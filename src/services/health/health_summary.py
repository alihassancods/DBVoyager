from typing import Any


class HealthSummaryService:

    @staticmethod
    def calculate_score(
        findings: list[dict[str, Any]],
    ) -> int:

        score = 100

        for finding in findings:

            severity = (
                finding.get("severity", "")
                .lower()
            )

            if severity == "critical":
                score -= 15

            elif severity == "warning":
                score -= 5

            elif severity == "info":
                score -= 1

        return max(score, 0)

    @staticmethod
    def get_status_label(score: int) -> str:
        """Translates a numeric score into a non-technical manager status label."""
        if score >= 90:
            return "EXCELLENT"
        elif score >= 75:
            return "STABLE"
        elif score >= 50:
            return "WARNING"
        else:
            return "CRITICAL"

    @staticmethod
    def top_findings(
        findings: list[dict[str, Any]],
        limit: int = 5,
    ) -> list[dict[str, Any]]:

        severity_order = {
            "critical": 3,
            "warning": 2,
            "info": 1,
        }

        return sorted(
            findings,
            key=lambda f: severity_order.get(
                f.get("severity", "").lower(),
                0,
            ),
            reverse=True,
        )[:limit]