"""Best-effort Redis cache for owner-checked dashboard resources."""

from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from typing import Any

from fastapi import Request, Response, status


CACHE_TTL_SECONDS = 60
PREVIEW_TTL_SECONDS = 86_400
PERSISTENCE_STREAM = "dbv:v1:persistence"


@lru_cache
def _client() -> Any | None:
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, socket_connect_timeout=0.05, socket_timeout=0.05)
    except Exception:
        return None


def _key(connection_id: str, resource: str) -> str:
    return f"dbv:v1:resource:{connection_id}:{resource}"


def _preview_key(connection_id: str, run_id: str) -> str:
    return f"dbv:v1:preview:{connection_id}:{run_id}"


def publish_preview(connection_id: str, run_id: str, collection_kind: str, report: Any) -> bool:
    """Durably hand a collected report to the persistence worker."""
    client = _client()
    if client is None:
        return False
    try:
        client.set(_preview_key(connection_id, run_id), json.dumps(report, default=str), ex=PREVIEW_TTL_SECONDS)
        client.xadd(PERSISTENCE_STREAM, {"run_id": run_id, "connection_id": connection_id, "collection_kind": collection_kind})
        return True
    except Exception:
        return False


def read_preview(connection_id: str, run_id: str) -> Any | None:
    client = _client()
    if client is None:
        return None
    try:
        value = client.get(_preview_key(connection_id, run_id))
        return json.loads(value) if value else None
    except Exception:
        return None


def warm_json(connection_id: str, resource: str, payload: Any) -> None:
    """Best-effort write-through after a Neon transaction has committed."""
    client = _client()
    if client is None:
        return
    body = json.dumps(payload, default=str, separators=(",", ":")).encode()
    try:
        client.hset(_key(connection_id, resource), mapping={"body": body, "etag": hashlib.sha256(body).hexdigest()})
        client.expire(_key(connection_id, resource), CACHE_TTL_SECONDS)
    except Exception:
        return


def invalidate(connection_id: str, *resources: str) -> None:
    client = _client()
    if client is None:
        return
    try:
        client.unlink(*[_key(connection_id, resource) for resource in resources])
    except Exception:
        return


def cached_json(request: Request, connection_id: str, resource: str, payload: Any) -> Response:
    """Return JSON bytes from Redis when available; ownership is checked by the route first."""
    client = _client()
    key = _key(connection_id, resource)
    body: bytes | None = None
    etag: str | None = None
    cache_state = "BYPASS"
    if client is not None:
        try:
            entry = client.hgetall(key)
            body, etag = entry.get(b"body"), entry.get(b"etag")
            if body and etag:
                etag = etag.decode()
                cache_state = "HIT"
            else:
                body = None
        except Exception:
            body = None

    if body is None:
        body = json.dumps(payload, default=str, separators=(",", ":")).encode()
        etag = hashlib.sha256(body).hexdigest()
        cache_state = "MISS" if client is not None else "BYPASS"
        if client is not None:
            try:
                client.hset(key, mapping={"body": body, "etag": etag})
                client.expire(key, CACHE_TTL_SECONDS)
            except Exception:
                pass

    headers = {
        "ETag": etag,
        "Cache-Control": f"private, max-age={CACHE_TTL_SECONDS}, must-revalidate",
        "X-Cache": cache_state,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)
