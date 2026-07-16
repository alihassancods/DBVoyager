"""Print a DeepSeek business summary for one PostgreSQL table."""

import argparse
import os

from src.agent import TableBusinessSummaryAgent
from src.db_engine.connection import get_connection


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize a PostgreSQL table.")
    parser.add_argument("table_name", help="Table name in the public schema")
    parser.add_argument("--database", default=os.getenv("DB_NAME"))
    args = parser.parse_args()
    if not args.database:
        parser.error("--database is required when DB_NAME is not configured")

    summary = TableBusinessSummaryAgent().summarize_database_table(
        args.table_name, lambda: get_connection(args.database)
    )
    print(summary)


if __name__ == "__main__":
    main()
