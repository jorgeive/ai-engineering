"""Post-generation checks for grounded estimates (Session 9).

Two independent guards run after the LLM returns an :class:`Estimate`:

* :func:`validate_citations` — every cited ``source_id`` must correspond to a
  chunk that was actually retrieved. Fabricated ids are the classic grounding
  failure and trigger one corrective retry in the orchestrator.
* :func:`check_coherence` — the ``insufficient`` confidence level has a strict
  shape (no numbers, an explanation present); a violation is a malformed
  response, not a valid estimate.
"""

from __future__ import annotations

from app.generation.rag.schemas import CitationReport, Estimate, RetrievedChunk, LineCitation


def validate_citations(
    estimate: Estimate,
    retrieved_chunks: list[RetrievedChunk],
) -> list[int]:
    """Return the cited source ids that were never retrieved (fabricated).

    Checks both the top-level ``sources`` citations and the per-task
    ``modules[].tasks[].sources``. An empty list means every citation is valid
    (including the edge case of an estimate that cites nothing at all).

    Parameters
    ----------
    estimate:
        The generated estimate to inspect.
    retrieved_chunks:
        The chunks the estimate was supposed to be grounded in.

    Returns
    -------
    list[str]
        Sorted, de-duplicated fabricated chunk ids (empty if all valid).
    """
    valid_ids = {str(chunk.id) for chunk in retrieved_chunks}

    cited_ids: set[str] = {str(citation.source_id) for citation in estimate.sources}
    for module in estimate.modules:
        for task in module.tasks:
            cited_ids.update(str(source.chunk_id) for source in task.sources)

    fabricated = cited_ids - valid_ids
    return sorted(int(value) if value.isdigit() else value for value in fabricated)


def check_coherence(estimate: Estimate) -> bool:
    """Return whether the estimate's confidence level matches its content.

    When ``confidence == "insufficient"``: both numeric totals must be ``None``,
    ``modules`` must be empty, and ``insufficient_context_explanation`` must be
    non-empty. Any other confidence level is always considered coherent here
    (the numeric checks belong to the schema/business rules, not to this guard).
    """
    if estimate.confidence != "insufficient":
        return True
    return (
        estimate.total_engineer_days is None
        and estimate.duration_weeks is None
        and not estimate.modules
        and bool(estimate.insufficient_context_explanation)
    )


def verify_citations(estimate: Estimate, retrieved_ids: set[str]) -> CitationReport:
    """Verify every line-level citation resolves to the retrieved context."""
    lines: list[LineCitation] = []
    verified = 0
    dangling: set[str] = set()
    global_cited = {str(citation.source_id) for citation in estimate.sources}
    global_missing = global_cited - retrieved_ids
    dangling.update(global_missing)
    verified += len(global_cited & retrieved_ids)
    for module in estimate.modules:
        for task in module.tasks:
            cited = [str(source.chunk_id) for source in task.sources]
            missing = sorted(set(cited) - retrieved_ids)
            verified += sum(1 for chunk_id in cited if chunk_id in retrieved_ids)
            status = "dangling" if missing else ("grounded" if task.grounded else "insufficient")
            lines.append(
                LineCitation(
                    module=module.name,
                    component=task.name,
                    status=status,
                    cited_chunk_ids=cited,
                    dangling_chunk_ids=missing,
                )
            )
            dangling.update(missing)
    return CitationReport(
        total_lines=len(lines),
        grounded_lines=sum(line.status == "grounded" for line in lines),
        dangling_lines=sum(line.status == "dangling" for line in lines),
        insufficient_lines=sum(line.status == "insufficient" for line in lines),
        verified_citations=verified,
        dangling_citations=sorted(dangling),
        lines=lines,
    )
