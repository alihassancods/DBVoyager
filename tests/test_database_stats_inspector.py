from src.db_engine.connection import get_connection

from src.db_engine.inspectors.statistics.database_stats_inspector import (
    DatabaseStatsInspector,
)


def main():

    inspector = DatabaseStatsInspector(
        connection_provider=get_connection
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