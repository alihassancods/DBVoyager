from src.db_engine.connection import get_connection

from src.db_engine.inspectors.statistics.statistics_inspector import (
    StatisticsInspector,
)


def main():

    inspector = StatisticsInspector(
        connection_provider=get_connection
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