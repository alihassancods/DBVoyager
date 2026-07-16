"""Tests for the table-summary CLI."""

import sys

import main


def test_main_prints_summary_for_requested_table(monkeypatch: object, capsys: object) -> None:
    requested: list[str] = []

    class FakeAgent:
        def summarize_database_table(self, table_name: str, _provider: object) -> str:
            requested.append(table_name)
            return "Orders store purchases. They support fulfilment."

    monkeypatch.setattr(main, "TableBusinessSummaryAgent", FakeAgent)
    monkeypatch.setattr(sys, "argv", ["main.py", "orders", "--database", "demo"])

    main.main()

    assert requested == ["orders"]
    assert capsys.readouterr().out == "Orders store purchases. They support fulfilment.\n"
