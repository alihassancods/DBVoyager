from psycopg2.extras import RealDictCursor

from src.db_engine.connection import get_connection

from src.models.database_models import (
    QueryResult
)

# now this one will be use to execute the query and return the result in a structured format using the QueryResult model. 
# It will take the database name and the query as input parameters, establish a connection to the specified database, execute the query, fetch all rows, and then close the connection. 
# Finally, it will return an instance of QueryResult containing the success status, executed query, fetched rows, and row count.

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