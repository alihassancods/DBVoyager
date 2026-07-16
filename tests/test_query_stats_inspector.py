import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db_engine.connection import get_connection
from src.db_engine.inspectors.statistics.query_stats_inspector import (
    QueryStatsInspector,
)

load_dotenv()

db_name = os.getenv("DB_NAME", "postgres")


def main():

    inspector = QueryStatsInspector(
        lambda: get_connection(database_name=db_name)
    )

    stats = inspector.get_query_stats()

    print(f"Found {len(stats)} query statistics\n")

    for stat in stats[:10]:
        print(stat)


if __name__ == "__main__":
    main()