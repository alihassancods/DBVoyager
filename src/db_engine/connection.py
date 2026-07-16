import os
from urllib.parse import urlparse

import psycopg2

from dotenv import load_dotenv #type:ignore

load_dotenv()

# this one is to make the secure connection to the database. It will take all the parameters from the .env file

def get_connection(database_name: str | None = None):
    """Create a PostgreSQL connection from the configured environment.

    ``DB_HOST`` may be either a hostname or a URL copied from a provider's
    dashboard. psycopg2 expects only the hostname, so a URL scheme is removed.
    """
    configured_host = os.getenv("DB_HOST", "")
    parsed_host = urlparse(configured_host)
    host = parsed_host.hostname if parsed_host.scheme else configured_host

    return psycopg2.connect(
        host=host,
        port=os.getenv("DB_PORT"),
        database=database_name or os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        sslmode="require",
        connect_timeout=10,
    )
