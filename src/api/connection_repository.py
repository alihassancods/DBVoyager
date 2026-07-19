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


def _app_connection() -> Any:
    database_url = os.getenv("APP_DATABASE_URL")
    if not database_url:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="APP_DATABASE_URL is not configured")
    return psycopg2.connect(database_url, connect_timeout=10)


def list_connections(auth_subject: str) -> list[dict[str, Any]]:
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT databases.id, databases.display_name, databases.status, databases.last_collected_at,
                       databases.database_size_mb, databases.num_connections, databases.archived_at,
                       databases.cache_hit_ratio, credentials.encrypted_data_key, credentials.ciphertext,
                       credentials.nonce, credentials.auth_tag
                FROM monitored_databases AS databases
                JOIN users ON users.id = databases.owner_user_id
                LEFT JOIN database_credentials AS credentials
                    ON credentials.monitored_database_id = databases.id AND credentials.is_active
                WHERE users.auth_subject = %s AND databases.deleted_at IS NULL
                ORDER BY databases.updated_at DESC
            """, (auth_subject,))
            rows = cursor.fetchall()
    return [_connection_metadata_from_row(row) for row in rows]


def connection_metadata(connection_id: str, auth_subject: str) -> dict[str, Any]:
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT databases.id, databases.display_name, databases.status, databases.last_collected_at,
                       databases.database_size_mb, databases.num_connections, databases.archived_at,
                       databases.cache_hit_ratio, credentials.encrypted_data_key, credentials.ciphertext,
                       credentials.nonce, credentials.auth_tag
                FROM monitored_databases AS databases
                JOIN users ON users.id = databases.owner_user_id
                LEFT JOIN database_credentials AS credentials
                    ON credentials.monitored_database_id = databases.id AND credentials.is_active
                WHERE databases.id = %s AND users.auth_subject = %s
            """, (connection_id, auth_subject))
            row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Database not found")
    return _connection_metadata_from_row(row)


def _connection_metadata_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    connection_id = str(row[0])
    credentials = _decode_credentials(connection_id, row[8:12]) if all(row[8:12]) else {}
    return {
        "connection_id": connection_id,
        "display_name": row[1],
        "status": row[2],
        "last_analyzed_at": row[3],
        "database_size_mb": row[4],
        "num_connections": row[5],
        "archived_at": row[6],
        "cache_hit_ratio": row[7],
        "host": credentials.get("host"),
        "port": credentials.get("port"),
        "database": credentials.get("database"),
    }


def rename_connection(connection_id: str, auth_subject: str, display_name: str) -> dict[str, Any]:
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE monitored_databases AS databases SET display_name = %s
                FROM users WHERE databases.owner_user_id = users.id
                  AND databases.id = %s AND users.auth_subject = %s AND databases.deleted_at IS NULL
                RETURNING databases.id
            """, (display_name, connection_id, auth_subject))
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Database not found")
    return connection_metadata(connection_id, auth_subject)


def set_archived(connection_id: str, auth_subject: str, archived: bool) -> None:
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE monitored_databases AS databases
                SET archived_at = CASE WHEN %s THEN now() ELSE NULL END
                FROM users WHERE databases.owner_user_id = users.id
                  AND databases.id = %s AND users.auth_subject = %s AND databases.deleted_at IS NULL
            """, (archived, connection_id, auth_subject))
            if cursor.rowcount != 1:
                raise HTTPException(status_code=404, detail="Database not found")


def _decode_credentials(connection_id: str, row: tuple[Any, ...] | None) -> dict[str, Any]:
    if row is None:
        raise HTTPException(status_code=404, detail="Database not found")
    encrypted_data_key, ciphertext, nonce, auth_tag = row
    try:
        wrapped = bytes(encrypted_data_key)
        data_key = AESGCM(_master_key()).decrypt(wrapped[:12], wrapped[12:], connection_id.encode())
        plaintext = AESGCM(data_key).decrypt(bytes(nonce), bytes(ciphertext) + bytes(auth_tag), connection_id.encode())
        credentials = json.loads(plaintext)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Could not decrypt connection credentials") from exc
    if not isinstance(credentials, dict):
        raise HTTPException(status_code=500, detail="Stored connection credentials are invalid")
    return credentials


def load_connection_credentials(connection_id: str, auth_subject: str) -> dict[str, Any]:
    """Decrypt the active credential record for its owning user only."""
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT credentials.encrypted_data_key, credentials.ciphertext, credentials.nonce, credentials.auth_tag
                FROM database_credentials AS credentials
                JOIN monitored_databases AS databases ON databases.id = credentials.monitored_database_id
                JOIN users ON users.id = databases.owner_user_id
                WHERE credentials.monitored_database_id = %s AND credentials.is_active
                  AND databases.deleted_at IS NULL AND users.auth_subject = %s
            """, (connection_id, auth_subject))
            row = cursor.fetchone()
    return _decode_credentials(connection_id, row)


def load_worker_connection_credentials(connection_id: str) -> dict[str, Any]:
    """Internal worker-only credential access after the scheduler has claimed a run."""
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT encrypted_data_key, ciphertext, nonce, auth_tag
                   FROM database_credentials
                   WHERE monitored_database_id = %s AND is_active""",
                (connection_id,),
            )
            row = cursor.fetchone()
    return _decode_credentials(connection_id, row)
