from src.db_engine.connection import get_connection

from src.db_engine.inspectors.statistics.lock_stats_inspector import (
    LockStatsInspector,
)


def main():

    inspector = LockStatsInspector(
        connection_provider=get_connection
    )

    stats = inspector.get_lock_stats()

    print(f"\nFound {len(stats)} locks\n")

    for stat in stats:
        print(stat)


if __name__ == "__main__":
    main()