from psycopg2.extras import RealDictCursor

from src.db_engine.connection import get_connection

from src.models.database_models import (
    QueryResult
)
def execute_query(
    database_name: str,
    query: str
):

    conn = get_connection(
        database_name
    )

    cursor = conn.cursor(
        cursor_factory=RealDictCursor
    )

    cursor.execute(query)

    rows = cursor.fetchall()

    conn.close()

    return QueryResult(
        success=True,
        query=query,
        rows=rows,
        row_count=len(rows)
    )