# src/db_engine/connection.py

import os

import psycopg2
from dotenv import load_dotenv # type: ignore

load_dotenv("/home/ali/Projects/DBVoyager/DBVoyager/.env")


def get_connection(database_name: str):
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")

    if not all([host, port, user, password]):
        raise ValueError("Missing one or more database connection environment variables (DB_HOST, DB_PORT, DB_USER, DB_PASSWORD)")

    try:
        return psycopg2.connect(
            host=host,
            port=port,
            database=database_name,
            user=user,
            password=password,
            connect_timeout=10
        )
    except psycopg2.OperationalError as e:
        raise ConnectionError(f"Could not connect to database '{database_name}' at {host}:{port}. "
                              f"Ensure the server is running and accepting connections. "
                              f"Original error: {e}") from e
