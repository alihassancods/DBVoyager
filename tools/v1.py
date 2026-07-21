"""Create one PostgreSQL health, statistics, schema, and visualization report.

Run with ``python v1.py`` (uses ``DB_NAME``) or
``python v1.py --database my_database``.  The complete report is written to
``result.txt`` by default as readable JSON.
"""

import argparse
import json
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.db_engine.connection import get_connection
from src.db_engine.inspectors.schema_inspector import SchemaInspector
from src.db_engine.inspectors.statistics.statistics_inspector import StatisticsInspector
from src.db_engine.visualizers.schema_visualizer import SchemaVisualizer
from src.models.statistics.statistics_snapshot_model import StatisticsSnapshot
from tools.health import audit_connection


ConnectionProvider = Callable[[], Any]
ProgressCallback = Callable[[str, str], None]
SectionCallback = Callable[[str, dict[str, Any]], None]


class _SharedConnection:
    """Prevent legacy inspectors from closing the job-scoped target connection."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def close(self) -> None:
        return None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


def _connection_provider(database_name: str) -> ConnectionProvider:
    """Return fresh connections because the existing inspectors close theirs."""
    return lambda: get_connection(database_name)


def _run_health_checks(
    connection_provider: ConnectionProvider,
    statistics_snapshot: StatisticsSnapshot,
    schema: Any | None,
) -> list[dict[str, str]]:
    """Apply health checks to the snapshots already collected for this report."""
    connection = connection_provider()
    try:
        connection.set_session(readonly=True, autocommit=True)
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = '5000ms'")
            cursor.execute("SET lock_timeout = '1000ms'")
        return audit_connection(connection, statistics_snapshot, schema)
    finally:
        connection.close()


def _inspect_with_connection(connection_provider: ConnectionProvider, callback: Callable[[ConnectionProvider], Any]) -> Any:
    """Give one inspector a dedicated, bounded read-only connection."""
    connection = connection_provider()
    try:
        connection.set_session(readonly=True, autocommit=True)
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = '5000ms'")
            cursor.execute("SET lock_timeout = '1000ms'")
        return callback(lambda: _SharedConnection(connection))
    finally:
        connection.close()


def _run_section(callback: Callable[[], Any]) -> dict[str, Any]:
    """Keep the report useful when one inspection section cannot be collected."""
    try:
        return {"status": "ok", "data": callback()}
    except Exception as exc:
        return {
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }


def build_report(
    database_name: str,
    connection_provider: ConnectionProvider | None = None,
    progress: ProgressCallback | None = None,
    sections: set[str] | None = None,
    section_ready: SectionCallback | None = None,
) -> dict[str, Any]:
    """Collect health findings, statistics, schema metadata, and a Mermaid ERD."""
    connection_provider = connection_provider or _connection_provider(database_name)
    report: dict[str, Any] = {
        "database": database_name,
        "generated_at": datetime.now(UTC).isoformat(),
    }

    requested = sections or {"statistics", "schema", "health_checks"}
    needs_statistics = "statistics" in requested or "health_checks" in requested
    needs_schema = "schema" in requested or "health_checks" in requested

    def add_section(name: str, value: dict[str, Any]) -> None:
        report[name] = value
        if section_ready:
            section_ready(name, value)

    def collect_statistics() -> StatisticsSnapshot:
        if progress:
            progress("statistics", "started")
        snapshot = _inspect_with_connection(
            connection_provider,
            lambda provider: StatisticsInspector(provider).get_snapshot(progress),
        )
        if progress:
            progress("statistics", "completed")
        return snapshot

    def collect_schema() -> Any:
        if progress:
            progress("schema", "started")
        schema = _inspect_with_connection(
            connection_provider,
            lambda provider: SchemaInspector.from_connection_provider(provider).inspect(progress),
        )
        if progress:
            progress("schema", "completed")
        return schema

    statistics_snapshot: StatisticsSnapshot | None = None
    schema = None
    if needs_statistics and needs_schema:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {executor.submit(collect_statistics): "statistics", executor.submit(collect_schema): "schema"}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    if name == "statistics":
                        statistics_snapshot = future.result()
                        add_section("statistics", {"status": "ok", "data": statistics_snapshot.model_dump(mode="json")})
                    else:
                        schema = future.result()
                        add_section("schema", {"status": "ok", "data": schema.model_dump(mode="json")})
                        add_section("schema_visualization", _run_section(lambda: SchemaVisualizer().render_mermaid(schema)))
                except Exception as exc:
                    add_section(name, {"status": "error", "error": f"{type(exc).__name__}: {exc}"})
                    if name == "schema":
                        add_section("schema_visualization", {"status": "skipped", "error": "Schema inspection did not complete."})
    elif needs_statistics:
        try:
            statistics_snapshot = collect_statistics()
            add_section("statistics", {"status": "ok", "data": statistics_snapshot.model_dump(mode="json")})
        except Exception as exc:
            add_section("statistics", {"status": "error", "error": f"{type(exc).__name__}: {exc}"})
    elif needs_schema:
        try:
            schema = collect_schema()
            add_section("schema", {"status": "ok", "data": schema.model_dump(mode="json")})
            add_section("schema_visualization", _run_section(lambda: SchemaVisualizer().render_mermaid(schema)))
        except Exception as exc:
            add_section("schema", {"status": "error", "error": f"{type(exc).__name__}: {exc}"})
            add_section("schema_visualization", {"status": "skipped", "error": "Schema inspection did not complete."})

    if "health_checks" in requested:
        if progress:
            progress("health_checks", "started")
        add_section("health_checks", (
            _run_section(lambda: _run_health_checks(connection_provider, statistics_snapshot, schema))
            if statistics_snapshot is not None
            else {"status": "skipped", "error": "Health checks require a statistics snapshot."}
        ))
        if progress:
            progress("health_checks", "completed")

    return report


def write_report(report: dict[str, Any], output_path: str | Path) -> Path:
    """Write the consolidated report and return its absolute path."""
    path = Path(output_path)
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    return path.resolve()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect a PostgreSQL health, stats, schema, and ERD report."
    )
    parser.add_argument("--database", default=os.getenv("DB_NAME"))
    parser.add_argument("--output", default="result.txt")
    args = parser.parse_args()

    if not args.database:
        parser.error("--database is required when DB_NAME is not configured")

    output_path = write_report(build_report(args.database), args.output)
    print(f"Report written to {output_path}")


if __name__ == "__main__":
    main()
