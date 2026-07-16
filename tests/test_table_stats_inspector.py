from src.db_engine.connection import get_connection

from src.db_engine.inspectors.statistics.table_stats_inspector import (
    TableStatsInspector,
)


def main():

    inspector = TableStatsInspector(
        connection_provider=get_connection
    )

    stats = inspector.get_table_stats()

    print(f"\nFound {len(stats)} tables\n")

    for stat in stats:
        print(stat)


if __name__ == "__main__":
    main()