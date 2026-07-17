"""Persistence for KPI proposals, approvals, and aggregate snapshots."""

import json
import os
from collections.abc import Callable
from typing import Any

import psycopg2

from .models import KPICandidate, KPIDefinition, KPISnapshot


def _app_connection() -> Any:
    database_url = os.getenv("APP_DATABASE_URL")
    if not database_url:
        raise RuntimeError("APP_DATABASE_URL is not configured")
    return psycopg2.connect(database_url, connect_timeout=10)


class KPIRepository:
    def __init__(self, connection_factory: Callable[[], Any] = _app_connection) -> None:
        self._connection_factory = connection_factory

    def save_candidates(
        self, monitored_database_id: str, schema_revision_id: str, candidates: list[KPICandidate]
    ) -> list[tuple[str, KPICandidate]]:
        saved: list[tuple[str, KPICandidate]] = []
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                for candidate in candidates:
                    candidate_json = json.dumps(candidate.model_dump())
                    cursor.execute(
                        """
                        SELECT id, status FROM kpi_candidates
                        WHERE monitored_database_id = %s AND schema_revision_id = %s
                          AND candidate_json = %s::jsonb
                        """,
                        (monitored_database_id, schema_revision_id, candidate_json),
                    )
                    existing = cursor.fetchone()
                    if existing is not None:
                        if existing[1] == "proposed":
                            saved.append((str(existing[0]), candidate))
                        continue
                    cursor.execute(
                        """
                        INSERT INTO kpi_candidates (
                            monitored_database_id, schema_revision_id, candidate_json, status
                        ) VALUES (%s, %s, %s, 'proposed')
                        RETURNING id
                        """,
                        (monitored_database_id, schema_revision_id, candidate_json),
                    )
                    saved.append((str(cursor.fetchone()[0]), candidate))
        return saved

    def approve(self, candidate_id: str) -> KPIDefinition:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE kpi_candidates SET status = 'approved', decided_at = now()
                    WHERE id = %s AND status = 'proposed'
                    RETURNING monitored_database_id, schema_revision_id, candidate_json
                    """,
                    (candidate_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ValueError("KPI candidate is not available for approval")
                monitored_database_id, schema_revision_id, candidate_json = row
                candidate = KPICandidate.model_validate(candidate_json)
                cursor.execute(
                    """
                    INSERT INTO kpi_definitions (
                        candidate_id, monitored_database_id, schema_revision_id, definition_json
                    ) VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (candidate_id, monitored_database_id, schema_revision_id, json.dumps(candidate.model_dump())),
                )
                definition_id = str(cursor.fetchone()[0])
        return KPIDefinition(
            id=definition_id,
            monitored_database_id=str(monitored_database_id),
            schema_revision_id=str(schema_revision_id),
            **candidate.model_dump(),
        )

    def reject(self, candidate_id: str) -> None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE kpi_candidates SET status = 'rejected', decided_at = now()
                       WHERE id = %s AND status = 'proposed'""",
                    (candidate_id,),
                )
                if cursor.rowcount != 1:
                    raise ValueError("KPI candidate is not available for rejection")

    def list_candidates(self, monitored_database_id: str, status: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT id, candidate_json, status, created_at, decided_at
            FROM kpi_candidates
            WHERE monitored_database_id = %s
        """
        parameters: list[Any] = [monitored_database_id]
        if status is not None:
            query += " AND status = %s"
            parameters.append(status)
        query += " ORDER BY created_at DESC"
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, parameters)
                rows = cursor.fetchall()
        return [
            {
                "id": str(row[0]),
                **(row[1] if isinstance(row[1], dict) else json.loads(row[1])),
                "status": row[2],
                "created_at": row[3],
                "decided_at": row[4],
            }
            for row in rows
        ]

    def candidate_belongs_to(self, candidate_id: str, monitored_database_id: str) -> bool:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM kpi_candidates WHERE id = %s AND monitored_database_id = %s",
                    (candidate_id, monitored_database_id),
                )
                return cursor.fetchone() is not None

    def list_definitions(self, monitored_database_id: str) -> list[KPIDefinition]:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, schema_revision_id, definition_json
                    FROM kpi_definitions
                    WHERE monitored_database_id = %s AND active
                    ORDER BY created_at DESC
                    """,
                    (monitored_database_id,),
                )
                rows = cursor.fetchall()
        return [
            KPIDefinition(
                id=str(row[0]),
                monitored_database_id=monitored_database_id,
                schema_revision_id=str(row[1]),
                **(row[2] if isinstance(row[2], dict) else json.loads(row[2])),
            )
            for row in rows
        ]

    def get_definition(self, definition_id: str, monitored_database_id: str) -> KPIDefinition | None:
        definitions = self.list_definitions(monitored_database_id)
        return next((definition for definition in definitions if definition.id == definition_id), None)

    def latest_snapshot(self, definition_id: str) -> dict[str, Any] | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT analysis_run_id, points_json, row_count, execution_ms, created_at
                    FROM kpi_snapshots
                    WHERE kpi_definition_id = %s AND status = 'succeeded'
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (definition_id,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return {
            "analysis_run_id": str(row[0]) if row[0] is not None else None,
            "points": row[1] if isinstance(row[1], list) else json.loads(row[1]),
            "row_count": row[2],
            "execution_ms": row[3],
            "generated_at": row[4],
        }

    def save_snapshot(self, snapshot: KPISnapshot) -> None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO kpi_snapshots (
                        kpi_definition_id, analysis_run_id, sql_text, points_json, row_count, execution_ms, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'succeeded')
                    """,
                    (
                        snapshot.kpi_definition_id,
                        snapshot.analysis_run_id,
                        snapshot.sql,
                        json.dumps(snapshot.points, default=str),
                        len(snapshot.points),
                        snapshot.execution_ms,
                    ),
                )
