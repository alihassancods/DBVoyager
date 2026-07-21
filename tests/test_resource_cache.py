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

    def scan_iter(self, match: str):
        prefix = match.removesuffix("*")
        yield from (key for key in self.values if key.startswith(prefix))

    def unlink(self, *keys: str) -> None:
        for key in keys:
            self.values.pop(key, None)


def test_cached_json_reuses_bytes_and_honors_etag(monkeypatch) -> None:
    cache = FakeRedis()
    monkeypatch.setattr(resource_cache, "_client", lambda: cache)
    app = FastAPI()

    @app.get("/")
    def read(request: Request):
        return resource_cache.cached_json(request, "database-1", "overview", lambda: {"value": 1})

    client = TestClient(app)
    first = client.get("/")
    second = client.get("/")
    unchanged = client.get("/", headers={"If-None-Match": first.headers["etag"]})

    assert first.json() == {"value": 1}
    assert first.headers["x-cache"] == "MISS"
    assert second.headers["x-cache"] == "HIT"
    assert unchanged.status_code == 304


def test_cached_json_skips_the_builder_on_a_hit(monkeypatch) -> None:
    cache = FakeRedis()
    monkeypatch.setattr(resource_cache, "_client", lambda: cache)
    app = FastAPI()
    calls = 0

    @app.get("/")
    def read(request: Request):
        nonlocal calls
        def build() -> dict[str, int]:
            nonlocal calls
            calls += 1
            return {"value": calls}
        return resource_cache.cached_json(request, "database-1", "overview", build)

    client = TestClient(app)
    assert client.get("/").json() == {"value": 1}
    assert client.get("/").json() == {"value": 1}
    assert calls == 1


def test_preview_is_stored_before_its_durable_job_is_enqueued(monkeypatch) -> None:
    cache = FakeRedis()
    monkeypatch.setattr(resource_cache, "_client", lambda: cache)

    assert resource_cache.publish_preview("database-1", "run-1", "dashboard", {"ready": True})
    assert resource_cache.read_preview("database-1", "run-1") == {"ready": True}
    assert cache.stream == [{"run_id": "run-1", "connection_id": "database-1", "collection_kind": "dashboard"}]


def test_invalidate_clears_all_resource_variants(monkeypatch) -> None:
    cache = FakeRedis()
    monkeypatch.setattr(resource_cache, "_client", lambda: cache)
    for resource in ("health-checks", "health-checks:critical:all", "insights:10"):
        resource_cache.warm_json("database-1", resource, {})

    resource_cache.invalidate("database-1", "health-checks")

    assert set(cache.values) == {resource_cache._key("database-1", "insights:10")}


def test_cached_value_only_builds_on_a_cache_miss(monkeypatch) -> None:
    cache = FakeRedis()
    monkeypatch.setattr(resource_cache, "_client", lambda: cache)
    calls = 0

    def build() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"value": calls}

    resource = resource_cache.cache_resource("fix", {"check": "missing-index"})
    assert resource_cache.cached_value("database-1", resource, build, 3600) == {"value": 1}
    assert resource_cache.cached_value("database-1", resource, build, 3600) == {"value": 1}
    assert calls == 1
