from src.db_engine.connection import get_connection
from src.db_engine.inspectors.statistics.query_stats_inspector import (
    QueryStatsInspector,
)

inspector = QueryStatsInspector(
    connection_provider=get_connection
)


def main():

    inspector = QueryStatsInspector(
        lambda: get_connection()
    )

    stats = inspector.get_query_stats()

    print(f"Found {len(stats)} query statistics\n")

    for stat in stats[:10]:
        print(stat)


if __name__ == "__main__":
    main()