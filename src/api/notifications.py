"""Durable, agent-created in-app notifications and authenticated WebSockets."""

from __future__ import annotations

import asyncio
import json
import os
from collections import defaultdict
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field, field_validator

from .auth import current_user, verify_neon_token
from .resource_cache import _client


router = APIRouter(tags=["notifications"])
NOTIFICATION_CHANNEL = "dbv:v1:notifications"
CLAIM_TTL_SECONDS = 60


class AgentNotification(BaseModel):
    connection_id: str
    idempotency_key: str = Field(min_length=1, max_length=240)
    severity: str = Field(pattern="^(info|warning|critical)$")
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=2000)
    action_path: str | None = Field(default=None, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("action_path")
    @classmethod
    def relative_action_path(cls, value: str | None) -> str | None:
        if value is not None and (not value.startswith("/") or value.startswith("//")):
            raise ValueError("action_path must be a relative application path")
        return value


class NotificationRead(BaseModel):
    read: bool = True


def _connection() -> Any:
    url = os.getenv("APP_DATABASE_URL")
    if not url:
        raise HTTPException(status_code=503, detail="APP_DATABASE_URL is not configured")
    return psycopg2.connect(url, connect_timeout=10)


def _row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]), "connection_id": str(row[1]), "severity": row[2], "title": row[3],
        "body": row[4], "action_path": row[5], "metadata": row[6] or {},
        "delivered_at": row[7].isoformat() if row[7] else None, "read_at": row[8].isoformat() if row[8] else None,
        "created_at": row[9].isoformat(),
    }


def create_notification_for_connection(notification: AgentNotification) -> dict[str, Any]:
    """Trusted agent entry point. Recipient ownership is derived from connection_id."""
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO notifications (user_id, monitored_database_id, idempotency_key, severity, title, body, action_path, metadata)
                   SELECT databases.owner_user_id, databases.id, %s, %s, %s, %s, %s, %s::jsonb
                   FROM monitored_databases AS databases WHERE databases.id = %s AND databases.deleted_at IS NULL
                   ON CONFLICT (user_id, idempotency_key) DO NOTHING
                   RETURNING id, monitored_database_id, severity, title, body, action_path, metadata, delivered_at, read_at, created_at,
                             (SELECT auth_subject FROM users WHERE id = user_id)""",
                (notification.idempotency_key, notification.severity, notification.title, notification.body,
                 notification.action_path, json.dumps(notification.metadata), notification.connection_id),
            )
            created = cursor.fetchone()
            if created is None:
                cursor.execute(
                    """SELECT id, monitored_database_id, severity, title, body, action_path, metadata, delivered_at, read_at, created_at,
                              (SELECT auth_subject FROM users WHERE id = user_id)
                       FROM notifications WHERE idempotency_key = %s AND user_id = (
                           SELECT owner_user_id FROM monitored_databases WHERE id = %s)""",
                    (notification.idempotency_key, notification.connection_id),
                )
                created = cursor.fetchone()
            if created is None:
                raise ValueError("Notification connection was not found")
    payload, auth_subject = _row(created[:10]), created[10]
    client = _client()
    if client is not None:
        try:
            client.publish(NOTIFICATION_CHANNEL, json.dumps({"notification_id": payload["id"], "auth_subject": auth_subject}))
        except Exception:
            pass
    return payload


def _owner_id(cursor: Any, auth_subject: str) -> UUID | None:
    cursor.execute("SELECT id FROM users WHERE auth_subject = %s", (auth_subject,))
    value = cursor.fetchone()
    return value[0] if value else None


def claim_pending(auth_subject: str, claim_id: UUID, limit: int = 100) -> list[dict[str, Any]]:
    with _connection() as connection:
        with connection.cursor() as cursor:
            owner_id = _owner_id(cursor, auth_subject)
            if owner_id is None:
                return []
            cursor.execute(
                """WITH claimed AS (
                    SELECT id FROM notifications WHERE user_id = %s AND delivered_at IS NULL
                      AND (delivery_claimed_at IS NULL OR delivery_claimed_at < now() - interval '60 seconds')
                    ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT %s
                ) UPDATE notifications AS notification SET delivery_claim_id = %s, delivery_claimed_at = now()
                  FROM claimed WHERE notification.id = claimed.id
                  RETURNING notification.id, notification.monitored_database_id, notification.severity, notification.title,
                    notification.body, notification.action_path, notification.metadata, notification.delivered_at,
                    notification.read_at, notification.created_at""",
                (owner_id, limit, str(claim_id)),
            )
            return [_row(row) for row in cursor.fetchall()]


def mark_delivered(notification_id: str, claim_id: UUID) -> None:
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE notifications SET delivered_at = now(), delivery_claim_id = NULL, delivery_claimed_at = NULL
                              WHERE id = %s AND delivery_claim_id = %s""", (notification_id, str(claim_id)))


def release_claims(claim_id: UUID) -> None:
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE notifications SET delivery_claim_id = NULL, delivery_claimed_at = NULL
                              WHERE delivery_claim_id = %s AND delivered_at IS NULL""", (str(claim_id),))


def list_notifications(auth_subject: str, limit: int, before: str | None) -> tuple[list[dict[str, Any]], int]:
    with _connection() as connection:
        with connection.cursor() as cursor:
            owner_id = _owner_id(cursor, auth_subject)
            if owner_id is None:
                return [], 0
            cursor.execute(
                """SELECT id, monitored_database_id, severity, title, body, action_path, metadata, delivered_at, read_at, created_at
                   FROM notifications WHERE user_id = %s AND (%s::timestamptz IS NULL OR created_at < %s::timestamptz)
                   ORDER BY created_at DESC LIMIT %s""", (owner_id, before, before, limit),
            )
            items = [_row(row) for row in cursor.fetchall()]
            cursor.execute("SELECT count(*) FROM notifications WHERE user_id = %s AND read_at IS NULL", (owner_id,))
            return items, int(cursor.fetchone()[0])


def set_read(notification_id: str, auth_subject: str, read: bool) -> None:
    with _connection() as connection:
        with connection.cursor() as cursor:
            owner_id = _owner_id(cursor, auth_subject)
            cursor.execute("UPDATE notifications SET read_at = CASE WHEN %s THEN now() ELSE NULL END WHERE id = %s AND user_id = %s", (read, notification_id, owner_id))
            if cursor.rowcount != 1:
                raise HTTPException(status_code=404, detail="Notification not found")


class NotificationHub:
    def __init__(self) -> None:
        self.sockets: dict[str, dict[UUID, WebSocket]] = defaultdict(dict)
        self.lock = asyncio.Lock()

    async def register(self, subject: str, claim_id: UUID, websocket: WebSocket) -> None:
        async with self.lock:
            self.sockets[subject][claim_id] = websocket

    async def unregister(self, subject: str, claim_id: UUID) -> None:
        async with self.lock:
            self.sockets[subject].pop(claim_id, None)
            if not self.sockets[subject]:
                self.sockets.pop(subject, None)
        await asyncio.to_thread(release_claims, claim_id)

    async def deliver(self, subject: str, claim_id: UUID, websocket: WebSocket) -> None:
        for notification in await asyncio.to_thread(claim_pending, subject, claim_id):
            try:
                await websocket.send_json({"type": "notification", "notification": notification})
                await asyncio.to_thread(mark_delivered, notification["id"], claim_id)
            except Exception:
                await asyncio.to_thread(release_claims, claim_id)
                raise

    async def dispatch(self, subject: str) -> None:
        async with self.lock:
            sessions = list(self.sockets.get(subject, {}).items())
        for claim_id, websocket in sessions:
            try:
                await self.deliver(subject, claim_id, websocket)
                return
            except Exception:
                continue


hub = NotificationHub()


def _token_from_subprotocol(websocket: WebSocket) -> tuple[str, str] | None:
    for protocol in websocket.scope.get("subprotocols", []):
        if protocol.startswith("dbvoyager.jwt."):
            return protocol, protocol.removeprefix("dbvoyager.jwt.")
    return None


@router.websocket("/ws/notifications")
async def notification_socket(websocket: WebSocket) -> None:
    credentials = _token_from_subprotocol(websocket)
    if credentials is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    protocol, token = credentials
    try:
        user = verify_neon_token(token)
        subject = str(user["sub"])
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    claim_id = uuid4()
    await websocket.accept(subprotocol=protocol)
    await hub.register(subject, claim_id, websocket)
    try:
        await hub.deliver(subject, claim_id, websocket)
        while True:
            if (await websocket.receive())["type"] == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unregister(subject, claim_id)


@router.get("/notifications")
def notifications(limit: int = Query(default=50, ge=1, le=100), before: str | None = None, user: dict[str, object] = Depends(current_user)) -> dict[str, Any]:
    items, unread_count = list_notifications(str(user["sub"]), limit, before)
    return {"data": items, "unread_count": unread_count, "next_before": items[-1]["created_at"] if len(items) == limit else None}


@router.patch("/notifications/{notification_id}")
def update_notification(notification_id: str, payload: NotificationRead, user: dict[str, object] = Depends(current_user)) -> dict[str, bool]:
    set_read(notification_id, str(user["sub"]), payload.read)
    return {"ok": True}


async def notification_listener() -> None:
    """Fan out Redis wake-ups to sockets connected to this API process."""
    client = _client()
    if client is None:
        return
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    try:
        pubsub.subscribe(NOTIFICATION_CHANNEL)
        while True:
            message = await asyncio.to_thread(pubsub.get_message, timeout=1.0)
            if message and message.get("data"):
                try:
                    payload = json.loads(message["data"])
                    await hub.dispatch(str(payload["auth_subject"]))
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    continue
    finally:
        pubsub.close()
