import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db_engine.connection import get_connection
from src.db_engine.inspectors.statistics.statistics_inspector import (
    StatisticsInspector,
)

load_dotenv()

db_name = os.getenv("DB_NAME", "postgres")


def main():

    inspector = StatisticsInspector(
        connection_provider=lambda: get_connection(database_name=db_name)
    )

    snapshot = inspector.get_snapshot()

    print("\n===== DATABASE =====")
    print(snapshot.database_stats)

    print("\n===== QUERIES =====")
    print(f"Count: {len(snapshot.query_stats)}")

    print("\n===== TABLES =====")
    print(f"Count: {len(snapshot.table_stats)}")

    print("\n===== INDEXES =====")
    print(f"Count: {len(snapshot.index_stats)}")

    print("\n===== LOCKS =====")
    print(f"Count: {len(snapshot.lock_stats)}")


if __name__ == "__main__":
    main()