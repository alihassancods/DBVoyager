import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db_engine.connection import get_connection
from src.db_engine.inspectors.statistics.table_stats_inspector import (
    TableStatsInspector,
)

load_dotenv()

db_name = os.getenv("DB_NAME", "postgres")


def main():

    inspector = TableStatsInspector(
        connection_provider=lambda: get_connection(database_name=db_name)
    )

    stats = inspector.get_table_stats()

    print(f"\nFound {len(stats)} tables\n")

    for stat in stats:
        print(stat)


if __name__ == "__main__":
    main()