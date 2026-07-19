from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.api import resource_cache


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, dict[bytes, bytes]] = {}
        self.strings: dict[str, bytes] = {}
        self.stream: list[dict[str, str]] = []

    def hgetall(self, key: str) -> dict[bytes, bytes]:
        return self.values.get(key, {})

    def hset(self, key: str, mapping: dict[str, str | bytes]) -> None:
        self.values[key] = {name.encode(): value if isinstance(value, bytes) else value.encode() for name, value in mapping.items()}

    def expire(self, _key: str, _seconds: int) -> None:
        return None

    def set(self, key: str, value: str, ex: int) -> None:
        assert ex == resource_cache.PREVIEW_TTL_SECONDS
        self.strings[key] = value.encode()

    def get(self, key: str) -> bytes | None:
        return self.strings.get(key)

    def xadd(self, _stream: str, fields: dict[str, str]) -> None:
        self.stream.append(fields)


def test_cached_json_reuses_bytes_and_honors_etag(monkeypatch) -> None:
    cache = FakeRedis()
    monkeypatch.setattr(resource_cache, "_client", lambda: cache)
    app = FastAPI()

    @app.get("/")
    def read(request: Request):
        return resource_cache.cached_json(request, "database-1", "overview", {"value": 1})

    client = TestClient(app)
    first = client.get("/")
    second = client.get("/")
    unchanged = client.get("/", headers={"If-None-Match": first.headers["etag"]})

    assert first.json() == {"value": 1}
    assert first.headers["x-cache"] == "MISS"
    assert second.headers["x-cache"] == "HIT"
    assert unchanged.status_code == 304


def test_preview_is_stored_before_its_durable_job_is_enqueued(monkeypatch) -> None:
    cache = FakeRedis()
    monkeypatch.setattr(resource_cache, "_client", lambda: cache)

    assert resource_cache.publish_preview("database-1", "run-1", "dashboard", {"ready": True})
    assert resource_cache.read_preview("database-1", "run-1") == {"ready": True}
    assert cache.stream == [{"run_id": "run-1", "connection_id": "database-1", "collection_kind": "dashboard"}]
