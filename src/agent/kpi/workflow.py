"""Orchestration without HTTP concerns."""

from collections.abc import Callable
from typing import Any

from src.models.schema.schema_model import DatabaseSchema

from .discovery import KPIDiscoveryAgent
from .executor import KPIAggregateExecutor
from .models import KPICandidate, KPIDefinition, KPISnapshot
from .repository import KPIRepository


class KPIWorkflow:
    def __init__(
        self,
        repository: KPIRepository,
        discovery_agent: KPIDiscoveryAgent,
        executor_factory: Callable[[], KPIAggregateExecutor],
    ) -> None:
        self._repository = repository
        self._discovery_agent = discovery_agent
        self._executor_factory = executor_factory

    def discover(
        self,
        monitored_database_id: str,
        schema_revision_id: str,
        schema: DatabaseSchema,
        summaries: dict[tuple[str, str], str],
    ) -> list[KPICandidate]:
        candidates = self._discovery_agent.discover(schema, summaries)
        self._repository.save_candidates(monitored_database_id, schema_revision_id, candidates)
        return candidates

    def approve_and_refresh(self, candidate_id: str, analysis_run_id: str | None = None) -> KPISnapshot:
        definition: KPIDefinition = self._repository.approve(candidate_id)
        snapshot = self._executor_factory().execute(definition, analysis_run_id)
        self._repository.save_snapshot(snapshot)
        return snapshot

    def reject(self, candidate_id: str) -> None:
        self._repository.reject(candidate_id)
