"""Build deterministic synthetic PDF attachments for the stress runner.

The size in each filename is the approximate amount of extractable text, not
the compressed PDF byte size. That is what reaches the model after attachment
extraction. Generated PDFs are intentionally ignored by Git.

Run with ``uv run python -m evals.stress.fixtures.build_pdfs``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fpdf import FPDF
from pypdf import PdfReader


TARGETS_KB = (5, 20, 50, 100)
_FIXED_CREATION_DATE = datetime(2026, 1, 1, tzinfo=timezone.utc)
_PARAGRAPH = (
    "The supplier portal replaces the manual compliance workflow. Vendors upload "
    "certificates for review, expiration checks, and approval before purchase orders. "
    "Every state transition is recorded in an immutable audit log retained for seven "
    "years. The portal synchronises vendor master data with the ERP every fifteen "
    "minutes and requires single sign-on for internal users. Performance must remain "
    "under two seconds at the 95th percentile with two hundred concurrent users. "
)


def _extract_text_chars(path: Path) -> int:
    reader = PdfReader(str(path))
    return len("\n\n".join(page.extract_text() or "" for page in reader.pages))


def build_pdf(target_kb: int, output_path: Path) -> int:
    """Create one PDF and return its extracted-text character count."""
    pdf = FPDF()
    pdf.set_creation_date(_FIXED_CREATION_DATE)
    pdf.set_title("Synthetic attachment fixture")
    pdf.set_author("ai-engineering stress tests")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)

    target_chars = target_kb * 1024
    written_chars = 0
    while written_chars < target_chars:
        pdf.multi_cell(0, 5, _PARAGRAPH)
        written_chars += len(_PARAGRAPH)
        if written_chars < target_chars:
            pdf.ln(3)

    pdf.output(str(output_path))
    return _extract_text_chars(output_path)


def main() -> None:
    fixtures_dir = Path(__file__).parent
    for target_kb in TARGETS_KB:
        output_path = fixtures_dir / f"attach_{target_kb}kb.pdf"
        extracted_chars = build_pdf(target_kb, output_path)
        print(
            f"{output_path.name}: extracted_chars={extracted_chars} "
            f"file_bytes={output_path.stat().st_size}"
        )


if __name__ == "__main__":
    main()
