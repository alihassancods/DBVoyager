# src/db_engine/connection.py

import os
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv # type: ignore

load_dotenv("/home/ali/Projects/DBVoyager/DBVoyager/.env")


def get_connection(database_name: str | None = None):
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    database_name = database_name or os.getenv("DB_NAME")

    if not all([host, port, user, password, database_name]):
        raise ValueError("Missing one or more database connection environment variables")

    parsed_host = urlparse(host)
    sslmode = "require" if parsed_host.scheme == "https" else None
    host = parsed_host.hostname or host

    options = {"host": host, "port": port, "database": database_name, "user": user, "password": password, "connect_timeout": 10}
    if sslmode:
        options["sslmode"] = sslmode

    try:
        return psycopg2.connect(**options)
    except psycopg2.OperationalError as e:
        raise ConnectionError(f"Could not connect to database '{database_name}' at {host}:{port}. "
                              f"Ensure the server is running and accepting connections. "
                              f"Original error: {e}") from e
