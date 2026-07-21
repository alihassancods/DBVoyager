import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from src.api.notifications import AgentNotification, _token_from_subprotocol, hub, notification_socket


def test_agent_notification_requires_relative_action_path() -> None:
    with pytest.raises(ValidationError):
        AgentNotification(
            connection_id="connection-1", idempotency_key="finding-1", severity="warning",
            title="Connection pressure", body="Review pooled connections.", action_path="//example.com",
        )


def test_websocket_token_comes_only_from_notification_subprotocol() -> None:
    websocket = SimpleNamespace(scope={"subprotocols": ["other", "dbvoyager.jwt.header.payload.signature"]})
    assert _token_from_subprotocol(websocket) == ("dbvoyager.jwt.header.payload.signature", "header.payload.signature")


def test_notification_socket_stops_after_disconnect_message() -> None:
    websocket = SimpleNamespace(
        scope={"subprotocols": ["dbvoyager.jwt.header.payload.signature"]},
        accept=AsyncMock(), receive=AsyncMock(return_value={"type": "websocket.disconnect"}),
    )
    with patch("src.api.notifications.verify_neon_token", return_value={"sub": "user"}), \
         patch.object(hub, "register", new=AsyncMock()) as register, \
         patch.object(hub, "deliver", new=AsyncMock()) as deliver, \
         patch.object(hub, "unregister", new=AsyncMock()) as unregister:
        asyncio.run(notification_socket(websocket))

    websocket.receive.assert_awaited_once()
    register.assert_awaited_once()
    deliver.assert_awaited_once()
    unregister.assert_awaited_once()


def test_notification_socket_replies_to_heartbeat() -> None:
    websocket = SimpleNamespace(
        scope={"subprotocols": ["dbvoyager.jwt.header.payload.signature"]},
        accept=AsyncMock(), send_json=AsyncMock(),
        receive=AsyncMock(side_effect=[{"type": "websocket.receive", "text": '{"type":"ping"}'}, {"type": "websocket.disconnect"}]),
    )
    with patch("src.api.notifications.verify_neon_token", return_value={"sub": "user"}), \
         patch.object(hub, "register", new=AsyncMock()), patch.object(hub, "deliver", new=AsyncMock()), \
         patch.object(hub, "unregister", new=AsyncMock()):
        asyncio.run(notification_socket(websocket))

    websocket.send_json.assert_awaited_once_with({"type": "pong"})
