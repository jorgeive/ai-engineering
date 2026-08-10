from evals.stress.metrics import MemoryDriftMetric
from evals.stress.scenarios import GROWING


def test_scenario_fact_carries_its_canonical_value_and_field() -> None:
    _turn_index, _transcript, fact = GROWING[0]
    assert fact == ("Nimbus", "project_name")

    assert fact is not None
    value, field = fact
    metric = MemoryDriftMetric(value, fact_field=field)
    result = metric.evaluate({"metadata": {"project_name": "Nimbus"}})

    assert result.passed is True
