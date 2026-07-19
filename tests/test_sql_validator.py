from src.agent.business_intelligence.validator import SQLValidator


def test_rejects_side_effecting_select_functions() -> None:
    result = SQLValidator().validate("SELECT pg_backup_stop()")

    assert not result.is_valid
    assert result.reason == "Side-effecting function detected."


def test_allows_read_only_select_function() -> None:
    assert SQLValidator().validate("SELECT pg_database_size(current_database())").is_valid


def test_rejects_select_into_and_locks() -> None:
    validator = SQLValidator()

    assert not validator.validate("SELECT id INTO copied_orders FROM orders").is_valid
    assert not validator.validate("SELECT * FROM orders FOR UPDATE").is_valid
