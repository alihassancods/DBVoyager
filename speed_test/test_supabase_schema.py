"""Live performance and latency benchmark for SchemaInspector against Supabase."""

import os
import time
import pytest
from dotenv import load_dotenv

from src.db_engine.connection import get_connection
from src.db_engine.inspectors.column_inspector import ColumnInspector
from src.db_engine.inspectors.index_inspector import IndexInspector
from src.db_engine.inspectors.key_inspector import KeyInspector
from src.db_engine.inspectors.relation_inspector import RelationInspector
from src.db_engine.inspectors.schema_inspector import SchemaInspector
from src.db_engine.inspectors.table_inspector import TableInspector

load_dotenv()


def _get_conn():
    return get_connection()


@pytest.mark.skipif(
    not (os.getenv("DB_HOST") or os.getenv("DATABASE_URL")),
    reason="Supabase database credentials not configured in .env",
)
def test_supabase_schema_inspection_benchmark():
    """Profiles network connection time, individual sub-inspectors, and total inspection latency."""

    print("\n" + "=" * 65)
    print("🚀 DBVoyager: Supabase Schema Inspector Performance Profile")
    print("=" * 65)

    # 1. Connection Handshake Latency
    t0 = time.perf_counter()
    conn = _get_conn()
    conn.close()
    conn_time_ms = (time.perf_counter() - t0) * 1000
    print(f"🔌 Supabase Handshake Time : {conn_time_ms:.2f} ms")
    print("-" * 65)

    print(f"{'Inspector Component':<25} | {'Latency (ms)':<15}")
    print("-" * 65)

    total_sub_ms = 0.0

    # 2. Table Inspector
    t_start = time.perf_counter()
    tables = TableInspector(_get_conn).get_tables()
    elapsed = (time.perf_counter() - t_start) * 1000
    total_sub_ms += elapsed
    print(f"{'TableInspector':<25} | {elapsed:>10.2f} ms")

    # 3. Column Inspector
    t_start = time.perf_counter()
    columns = ColumnInspector(_get_conn).get_columns()
    elapsed = (time.perf_counter() - t_start) * 1000
    total_sub_ms += elapsed
    print(f"{'ColumnInspector':<25} | {elapsed:>10.2f} ms")

    # 4. Key Inspector (Primary Keys)
    key_inspector = KeyInspector(_get_conn)
    t_start = time.perf_counter()
    primary_keys = key_inspector.get_primary_keys()
    elapsed = (time.perf_counter() - t_start) * 1000
    total_sub_ms += elapsed
    print(f"{'KeyInspector (PKs)':<25} | {elapsed:>10.2f} ms")

    # 5. Key Inspector (Foreign Keys)
    t_start = time.perf_counter()
    foreign_keys = key_inspector.get_foreign_keys()
    elapsed = (time.perf_counter() - t_start) * 1000
    total_sub_ms += elapsed
    print(f"{'KeyInspector (FKs)':<25} | {elapsed:>10.2f} ms")

    # 6. Index Inspector
    t_start = time.perf_counter()
    indexes = IndexInspector(_get_conn).get_indexes()
    elapsed = (time.perf_counter() - t_start) * 1000
    total_sub_ms += elapsed
    print(f"{'IndexInspector':<25} | {elapsed:>10.2f} ms")

    # 7. Relation Inspector (In-Memory Transformation)
    t_start = time.perf_counter()
    relations = RelationInspector().build_relations(foreign_keys)
    elapsed = (time.perf_counter() - t_start) * 1000
    total_sub_ms += elapsed
    print(f"{'RelationInspector':<25} | {elapsed:>10.2f} ms (in-memory)")

    print("-" * 65)

    # 8. Full Orchestrated SchemaInspector Run
    t_full_start = time.perf_counter()
    full_inspector = SchemaInspector.from_connection_provider(_get_conn)
    schema = full_inspector.inspect()
    full_elapsed_ms = (time.perf_counter() - t_full_start) * 1000

    print(f"⚡ Cumulative Sub-Runs Total     : {total_sub_ms:.2f} ms")
    print(f"🚀 Total SchemaInspector Run     : {full_elapsed_ms:.2f} ms ({full_elapsed_ms / 1000:.2f} s)")
    print("-" * 65)
    print(
        f"📊 Summary: Discovered {len(schema.tables)} tables, "
        f"{len(schema.columns)} columns, {len(schema.indexes)} indexes"
    )
    print("=" * 65)

    assert schema is not None
    assert len(schema.tables) == len(tables)


if __name__ == "__main__":
    test_supabase_schema_inspection_benchmark()