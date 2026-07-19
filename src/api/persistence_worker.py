"""Redis-backed persistence worker for collected dashboard reports."""

from __future__ import annotations

import os
from typing import Any

import psycopg2

from .analysis_repository import (
    _mark_failed,
    _record_progress,
    persist_collected_analysis,
    run_post_persist_enrichment,
)
from .connection_repository import load_worker_connection_credentials
from .resource_cache import PERSISTENCE_STREAM, _client, read_preview

GROUP = "dashboard-persistence"
CONSUMER = f"api-{os.getpid()}"


def process_persistence_jobs() -> None:
    """Process queued reports; unacknowledged messages remain durable in Redis."""
    client = _client()
    if client is None:
        return
    try:
        client.xgroup_create(PERSISTENCE_STREAM, GROUP, id="0", mkstream=True)
    except Exception:
        pass
    try:
        messages = client.xreadgroup(GROUP, CONSUMER, {PERSISTENCE_STREAM: ">"}, count=1, block=100)
    except Exception:
        return
    for _stream, entries in messages:
        for message_id, fields in entries:
            run_id = fields[b"run_id"].decode()
            connection_id = fields[b"connection_id"].decode()
            collection_kind = fields[b"collection_kind"].decode()
            report: Any = read_preview(connection_id, run_id)
            if report is None:
                _mark_failed(run_id, "Live preview expired before persistence")
                client.xack(PERSISTENCE_STREAM, GROUP, message_id)
                continue
            try:
                _record_progress(run_id, "persistence", "Persisting collected report.")
                persist_collected_analysis(run_id, connection_id, report, collection_kind, lambda stage, message: _record_progress(run_id, stage, message))
                _record_progress(run_id, "persistence", "Persisted collected report.")
                client.xack(PERSISTENCE_STREAM, GROUP, message_id)
                if collection_kind == "dashboard":
                    try:
                        credentials = load_worker_connection_credentials(connection_id)
                        run_post_persist_enrichment(
                            connection_id, run_id, report,
                            lambda: psycopg2.connect(**credentials, connect_timeout=10),
                        )
                    except Exception as exc:
                        _record_progress(run_id, "enrichment", f"Deferred enrichment skipped: {type(exc).__name__}.")
            except Exception as exc:
                attempts = int(fields.get(b"attempt", b"0")) + 1
                if attempts < 3:
                    client.xadd(PERSISTENCE_STREAM, {
                        "run_id": run_id, "connection_id": connection_id,
                        "collection_kind": collection_kind, "attempt": attempts,
                    })
                else:
                    _mark_failed(run_id, f"Persistence failed: {type(exc).__name__}: {exc}")
                client.xack(PERSISTENCE_STREAM, GROUP, message_id)
