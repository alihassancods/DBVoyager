import pytest

import v3
from src.agent.kpi.models import KPICandidate


def test_v3_requires_a_connection_id(monkeypatch) -> None:
    monkeypatch.delenv("DBVOYAGER_CONNECTION_ID", raising=False)

    with pytest.raises(RuntimeError, match="DBVOYAGER_CONNECTION_ID"):
        v3.main()


def test_v3_approval_checklist_executes_approved_candidate(capsys) -> None:
    class Workflow:
        def approve_and_refresh(self, candidate_id):
            assert candidate_id == "candidate-1"
            return type("Snapshot", (), {"sql": "SELECT 1", "points": [{"value": 1}], "execution_ms": 1.0})()

        def reject(self, _candidate_id):
            raise AssertionError("reject should not be called")

    candidate = KPICandidate(
        table_name="orders", measure_column="total", aggregation="sum", title="Revenue",
        rationale="Order totals", confidence=1,
    )
    v3.review_candidates([("candidate-1", candidate)], Workflow(), lambda _prompt: "a")

    assert "Approved and executed." in capsys.readouterr().out
