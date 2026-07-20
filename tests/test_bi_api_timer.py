"""Exercise the FastAPI BI investigation and SSE streaming endpoints with stage timing metrics."""

from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("DBVOYAGER_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
EMAIL = os.getenv("DBVOYAGER_EMAIL", "alihassan123@gmail.com")
PASSWORD = os.getenv("DBVOYAGER_PASSWORD", "hello123@")
CONNECTION_ID = os.getenv("DBVOYAGER_CONNECTION_ID", "")

QUESTION = os.getenv(
    "DBVOYAGER_BI_QUESTION", "Which product category generates the highest revenue?"
)


class ApiError(RuntimeError):
    """An HTTP error returned by the DBVoyager API."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def request_json(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    access_token: str | None = None,
    cookie: str | None = None,
    return_headers: bool = False,
) -> dict[str, Any] | tuple[dict[str, Any], dict[str, str]]:
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if access_token is not None:
        headers["Authorization"] = f"Bearer {access_token}"
    if cookie is not None:
        headers["Cookie"] = cookie

    request = Request(
        f"{API_BASE_URL}{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=45) as response:
            body = json.loads(response.read())
            if return_headers:
                return body, {name.lower(): value for name, value in response.headers.items()}
            return body
    except HTTPError as exc:
        body = exc.read().decode()
        try:
            message = json.loads(body).get("detail", body)
        except json.JSONDecodeError:
            message = body
        raise ApiError(exc.code, str(message)) from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach DBVoyager API at {API_BASE_URL}: {exc.reason}") from exc


def authenticate() -> str:
    """Authenticates with the DBVoyager API and returns a valid JWT access token."""
    print("Logging into DBVoyager API...")
    login_response, login_headers = request_json(
        "POST", "/auth/login", {"email": EMAIL, "password": PASSWORD}, return_headers=True
    )
    session_cookie = login_headers.get("set-cookie", "").split(";", 1)[0]
    if not session_cookie:
        raise RuntimeError("Auth login did not return a session cookie")

    _, token_headers = request_json(
        "POST", "/auth/token", cookie=session_cookie, return_headers=True
    )
    access_token = token_headers.get("set-auth-jwt")
    if not access_token:
        raise RuntimeError("Auth session did not return a JWT token")
    return str(access_token)


def resolve_connection_id(access_token: str) -> str:
    """Gets the existing connection_id or raises an error if none exists."""
    if CONNECTION_ID:
        return CONNECTION_ID

    connections = request_json("GET", "/connections", access_token=access_token)
    if isinstance(connections, list) and len(connections) > 0:
        return str(connections[0].get("connection_id") or connections[0].get("id"))
    elif isinstance(connections, dict) and connections.get("data"):
        return str(connections["data"][0]["connection_id"])

    raise RuntimeError("No target database connection found. Connect a database first.")


def stream_bi_investigation(
    connection_id: str, question: str, access_token: str
) -> dict[str, Any]:
    """Triggers the BI investigation SSE endpoint and benchmarks overall and per-stage timing metrics."""
    overall_start = time.perf_counter()
    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
    }

    url_path = f"/connections/{connection_id}/bi/investigations/stream"
    request = Request(
        f"{API_BASE_URL}{url_path}",
        data=json.dumps({"question": question}).encode(),
        headers=headers,
        method="POST",
    )

    stage_timings: dict[str, dict[str, float]] = {}
    final_result: dict[str, Any] = {}

    print("\n" + "=" * 80)
    print("STARTING BI API INVESTIGATION STREAM")
    print(f"Connection ID: {connection_id}")
    print(f"Question     : {question}")
    print("=" * 80)

    try:
        with urlopen(request, timeout=300) as response:
            current_event_type = "message"

            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue

                if line.startswith("event: "):
                    current_event_type = line[7:].strip()
                    continue

                if not line.startswith("data: "):
                    continue

                event_data = json.loads(line[6:])
                now = time.perf_counter()

                print(f"[{current_event_type.upper()}] {event_data}")

                if current_event_type == "stage":
                    stage_name = event_data.get("stage", "unknown")
                    status = event_data.get("status")

                    if status == "running":
                        stage_timings[stage_name] = {"start": now}
                        print(f"▶️  Stage [{stage_name.upper()}] started...")
                    elif status == "complete" and stage_name in stage_timings:
                        duration = now - stage_timings[stage_name]["start"]
                        stage_timings[stage_name]["duration"] = duration
                        print(f"⏱️ Stage [{stage_name.upper()}] completed in {duration:.3f}s")

                elif current_event_type == "complete":
                    final_result = event_data

    except URLError as exc:
        raise RuntimeError(f"Could not stream BI investigation: {exc.reason}") from exc

    total_duration = time.perf_counter() - overall_start

    # Print Timing Report
    print("\n" + "=" * 80)
    print("STAGE PERFORMANCE BENCHMARKS (API STREAM)")
    print("=" * 80)
    for stage, metrics in stage_timings.items():
        dur = metrics.get("duration", 0.0)
        print(f" • {stage.capitalize():<18}: {dur:.3f}s")
    print("-" * 40)
    print(f" TOTAL EXECUTION TIME  : {total_duration:.3f}s")
    print("=" * 80 + "\n")

    return final_result


def main() -> None:
    access_token = authenticate()
    conn_id = resolve_connection_id(access_token)
    result = stream_bi_investigation(conn_id, QUESTION, access_token)

    print("=" * 80)
    print("FINAL INVESTIGATION INSIGHT REPORT")
    print("=" * 80)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()