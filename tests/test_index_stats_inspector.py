from src.db_engine.connection import get_connection

from src.db_engine.inspectors.statistics.index_stats_inspector import (
    IndexStatsInspector,
)


def main():

    inspector = IndexStatsInspector(
        connection_provider=get_connection
    )

    stats = inspector.get_index_stats()

    print(f"\nFound {len(stats)} indexes\n")

    for stat in stats:
        print(stat)


if __name__ == "__main__":
    main()