"""
End-to-end test for Business Intelligence workflow.
"""

from src.agent.business_intelligence.orchestrator import (
    BusinessIntelligenceOrchestrator,
)

from src.db_engine.connection import (
    get_connection,
)


def test_business_question() -> None:
    """
    Test a complete BI investigation.
    """

    orchestrator = (
        BusinessIntelligenceOrchestrator(
            connection_provider=lambda: get_connection()
        )
    )

    result = orchestrator.investigate(
    question="Which product category generates the highest revenue?",
)

    print("\n")
    print("=" * 80)
    print("QUESTION")
    print("=" * 80)
    print(result["question"])

    print("\n")
    print("=" * 80)
    print("PLAN")
    print("=" * 80)
    print(result["plan"])

    print("\n")
    print("=" * 80)
    print("SQL")
    print("=" * 80)
    print(result["sql"])

    print("\n")
    print("=" * 80)
    print("ROWS")
    print("=" * 80)
    print(result["rows"])

    print("\n")
    print("=" * 80)
    print("INSIGHT")
    print("=" * 80)
    print(result["insight"])

    print("\n")
    print("=" * 80)
    print("CHARTS")
    print("=" * 80)
    print(result["charts"])

    assert result is not None