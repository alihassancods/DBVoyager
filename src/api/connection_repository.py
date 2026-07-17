"""Persist encrypted monitored-database connection settings."""

from __future__ import annotations

import base64
import json
import os
from secrets import token_bytes
from typing import Any

import psycopg2
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException, status


def _master_key() -> bytes:
    try:
        key = base64.urlsafe_b64decode(os.environ["APP_CREDENTIAL_MASTER_KEY"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="APP_CREDENTIAL_MASTER_KEY is not configured",
        ) from exc
    if len(key) != 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="APP_CREDENTIAL_MASTER_KEY must decode to 32 bytes",
        )
    return key


def _encrypt(connection_id: str, credentials: dict[str, Any]) -> dict[str, bytes | str | int]:
    data_key = token_bytes(32)
    payload_nonce = token_bytes(12)
    plaintext = json.dumps(credentials, separators=(",", ":")).encode()
    payload = AESGCM(data_key).encrypt(payload_nonce, plaintext, connection_id.encode())

    wrap_nonce = token_bytes(12)
    wrapped_key = AESGCM(_master_key()).encrypt(wrap_nonce, data_key, connection_id.encode())
    # ponytail: env-backed master key; replace APP_CREDENTIAL_MASTER_KEY with cloud KMS wrapping before multi-instance production.
    return {
        "encrypted_data_key": wrap_nonce + wrapped_key,
        "ciphertext": payload[:-16],
        "nonce": payload_nonce,
        "auth_tag": payload[-16:],
        "kms_key_ref": "env:APP_CREDENTIAL_MASTER_KEY",
        "key_version": 1,
    }


def save_connection(
    auth_subject: str,
    email: str | None,
    display_name: str,
    credentials: dict[str, Any],
) -> str:
    database_url = os.getenv("APP_DATABASE_URL")
    if not database_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="APP_DATABASE_URL is not configured",
        )
    try:
        with psycopg2.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO users (auth_subject, email)
                    VALUES (%s, %s)
                    ON CONFLICT (auth_subject) DO UPDATE
                    SET email = COALESCE(EXCLUDED.email, users.email)
                    RETURNING id
                    """,
                    (auth_subject, email),
                )
                user_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO monitored_databases (owner_user_id, display_name)
                    VALUES (%s, %s)
                    ON CONFLICT (owner_user_id, lower(display_name)) WHERE deleted_at IS NULL
                    DO UPDATE SET display_name = EXCLUDED.display_name
                    RETURNING id
                    """,
                    (user_id, display_name),
                )
                connection_id = str(cursor.fetchone()[0])
                encrypted = _encrypt(connection_id, credentials)
                cursor.execute(
                    """
                    UPDATE database_credentials
                    SET is_active = false, rotated_at = now()
                    WHERE monitored_database_id = %s AND is_active
                    """,
                    (connection_id,),
                )
                cursor.execute(
                    """
                    INSERT INTO database_credentials (
                        monitored_database_id, encrypted_data_key, ciphertext, nonce,
                        auth_tag, kms_key_ref, key_version, algorithm
                    ) VALUES (%(monitored_database_id)s, %(encrypted_data_key)s,
                              %(ciphertext)s, %(nonce)s, %(auth_tag)s,
                              %(kms_key_ref)s, %(key_version)s, 'AES-256-GCM')
                    """,
                    {"monitored_database_id": connection_id, **encrypted},
                )
        return connection_id
    except psycopg2.Error as exc:
        detail = exc.diag.message_primary or exc.__class__.__name__
        raise HTTPException(status_code=502, detail=f"Could not save the connection: {detail}") from exc
