"""
SQL safety validator for Business Intelligence agent.

Only READ queries are allowed.
"""

from dataclasses import dataclass
import re


@dataclass
class ValidationResult:
    is_valid: bool
    reason: str | None = None


class SQLValidator:

    FORBIDDEN_KEYWORDS = {
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "TRUNCATE",
        "CREATE",
        "REPLACE",
        "MERGE",
        "UPSERT",
        "GRANT",
        "REVOKE",
        "VACUUM",
        "ANALYZE",
        "COPY",
        "INTO",
    }

    FORBIDDEN_FUNCTIONS = {
        "pg_advisory_lock", "pg_advisory_xact_lock", "pg_backup_start", "pg_backup_stop",
        "pg_cancel_backend", "pg_create_restore_point", "pg_logical_emit_message", "pg_notify",
        "pg_promote", "pg_read_binary_file", "pg_read_file", "pg_reload_conf", "pg_rotate_logfile",
        "pg_sleep", "pg_start_backup", "pg_stop_backup", "pg_switch_wal", "pg_terminate_backend",
        "set_config",
    }

    def validate(
        self,
        sql: str,
    ) -> ValidationResult:
        """
        Ensure query is read-only.
        """

        cleaned_sql = sql.strip()
        if not cleaned_sql:
            return ValidationResult(is_valid=False, reason="SQL is required.")
        if "--" in cleaned_sql or "/*" in cleaned_sql or "*/" in cleaned_sql:
            return ValidationResult(is_valid=False, reason="SQL comments are not allowed.")
        if ";" in cleaned_sql.rstrip(";") or cleaned_sql.count(";") > 1:
            return ValidationResult(is_valid=False, reason="Only one statement is allowed.")
        cleaned_sql = cleaned_sql.rstrip(";").strip()
        sql_upper = cleaned_sql.upper()

        for keyword in self.FORBIDDEN_KEYWORDS:

            if re.search(
                rf"\b{keyword}\b",
                sql_upper,
            ):
                return ValidationResult(
                    is_valid=False,
                    reason=f"Forbidden keyword detected: {keyword}",
                )

        forbidden_functions = "|".join(function.upper() for function in self.FORBIDDEN_FUNCTIONS)
        if re.search(rf"\b(?:PG_CATALOG\.)?(?:{forbidden_functions})\s*\(", sql_upper) or re.search(
            r"\bDBLINK_\w*\s*\(", sql_upper
        ):
            return ValidationResult(is_valid=False, reason="Side-effecting function detected.")

        if not sql_upper.startswith(
            (
                "SELECT",
                "WITH",
            )
        ):
            return ValidationResult(
                is_valid=False,
                reason="Only SELECT statements are allowed.",
            )

        if re.search(r"\bWITH\b[\s\S]*\b(INSERT|UPDATE|DELETE|MERGE)\b", sql_upper):
            return ValidationResult(is_valid=False, reason="Data-modifying CTEs are not allowed.")

        if re.search(r"\bFOR\s+(UPDATE|SHARE|NO\s+KEY\s+UPDATE|KEY\s+SHARE)\b", sql_upper):
            return ValidationResult(is_valid=False, reason="Locking clauses are not allowed.")

        return ValidationResult(
            is_valid=True,
        )
