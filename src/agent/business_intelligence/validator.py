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
    }

    def validate(
        self,
        sql: str,
    ) -> ValidationResult:
        """
        Ensure query is read-only.
        """

        cleaned_sql = sql.strip()
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

        return ValidationResult(
            is_valid=True,
        )