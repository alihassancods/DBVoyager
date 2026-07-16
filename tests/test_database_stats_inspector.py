import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db_engine.connection import get_connection
from src.db_engine.inspectors.statistics.database_stats_inspector import (
    DatabaseStatsInspector,
)

load_dotenv()

db_name = os.getenv("DB_NAME", "postgres")


def main():

    inspector = DatabaseStatsInspector(
        connection_provider=lambda: get_connection(database_name=db_name)
    )

    stats = (
        inspector.get_database_stats()
    )

    print(
        f"\nFound {len(stats)} database stats\n"
    )

    for stat in stats:
        print(stat)


if __name__ == "__main__":
    main()