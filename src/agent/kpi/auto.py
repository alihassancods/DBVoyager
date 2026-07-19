"""Automatic KPI discovery and bounded aggregate collection."""

from collections.abc import Callable
from typing import Any

from .discovery import KPIDiscoveryAgent, KPIDiscoveryUnavailable
from .executor import KPIAggregateExecutor
from .repository import KPIRepository


def generate_kpis(
    monitored_database_id: str,
    connection_provider: Callable[[], Any],
    progress: Callable[[str, str], None] | None = None,
    analysis_run_id: str | None = None,
) -> int:
    """Persist and calculate metadata-derived KPIs without exposing customer rows to the agent."""
    repository = KPIRepository()
    repository.set_generation_status(monitored_database_id, "running", analysis_run_id)
    try:
        context = repository.current_schema_context(monitored_database_id)
        if context is None:
            repository.set_generation_status(monitored_database_id, "succeeded", analysis_run_id)
            return 0
        schema_revision_id, schema, summaries = context
        candidates = KPIDiscoveryAgent().discover(schema, summaries)
        saved = repository.save_candidates(monitored_database_id, schema_revision_id, candidates)
        for candidate_id, _ in saved:
            repository.approve(candidate_id, monitored_database_id)
        definitions = repository.list_definitions(monitored_database_id)
        for number, definition in enumerate(definitions, start=1):
            snapshot = KPIAggregateExecutor(connection_provider).execute(definition)
            repository.save_snapshot(snapshot)
            if progress:
                progress("kpis", f"Calculated KPI {number}/{len(definitions)}: {definition.title}.")
        repository.set_generation_status(monitored_database_id, "succeeded", analysis_run_id, len(definitions))
        return len(definitions)
    except KPIDiscoveryUnavailable:
        repository.set_generation_status(
            monitored_database_id, "unavailable", analysis_run_id,
            error_message="KPI generation is temporarily unavailable. Please try again later."
        )
        raise
    except Exception as exc:
        repository.set_generation_status(
            monitored_database_id, "failed", analysis_run_id,
            error_message=f"{type(exc).__name__}: {str(exc)[:200]}"
        )
        raise
