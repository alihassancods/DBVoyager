"""PostgreSQL queries for collecting database metadata."""

"""These are the queries used to collect metadata about tables, columns, primary keys, foreign keys, and indexes in a PostgreSQL database. 
The queries are designed to filter out system schemas and focus on user-visible objects."""

GET_TABLES_QUERY = """
SELECT
    tables.table_name,
    tables.table_schema AS schema_name,
    tables.table_type,
    CASE
        WHEN classes.reltuples < 0 THEN NULL
        ELSE classes.reltuples::bigint
    END AS estimated_rows
FROM information_schema.tables AS tables
LEFT JOIN pg_catalog.pg_namespace AS namespaces
    ON namespaces.nspname = tables.table_schema
LEFT JOIN pg_catalog.pg_class AS classes
    ON classes.relnamespace = namespaces.oid
    AND classes.relname = tables.table_name
WHERE tables.table_schema = 'public'
  AND tables.table_type IN ('BASE TABLE', 'VIEW', 'FOREIGN TABLE')
ORDER BY tables.table_schema, tables.table_name;
"""

GET_COLUMNS_QUERY = """
SELECT
    columns.table_name,
    columns.column_name,
    columns.data_type,
    columns.is_nullable = 'YES' AS is_nullable,
    columns.column_default,
    columns.ordinal_position
FROM information_schema.columns AS columns
WHERE columns.table_schema = 'public'
ORDER BY columns.table_schema, columns.table_name, columns.ordinal_position;
"""

GET_PRIMARY_KEYS_QUERY = """
SELECT
    key_columns.table_name,
    key_columns.column_name
FROM information_schema.table_constraints AS constraints
JOIN information_schema.key_column_usage AS key_columns
    ON key_columns.constraint_catalog = constraints.constraint_catalog
    AND key_columns.constraint_schema = constraints.constraint_schema
    AND key_columns.constraint_name = constraints.constraint_name
WHERE constraints.constraint_type = 'PRIMARY KEY'
  AND constraints.table_schema = 'public'
ORDER BY key_columns.table_schema, key_columns.table_name, key_columns.ordinal_position;
"""

GET_FOREIGN_KEYS_QUERY = """
SELECT
    source_columns.table_name AS source_table,
    source_columns.column_name AS source_column,
    target_columns.table_name AS target_table,
    target_columns.column_name AS target_column
FROM information_schema.referential_constraints AS referential_constraints
JOIN information_schema.key_column_usage AS source_columns
    ON source_columns.constraint_catalog = referential_constraints.constraint_catalog
    AND source_columns.constraint_schema = referential_constraints.constraint_schema
    AND source_columns.constraint_name = referential_constraints.constraint_name
JOIN information_schema.key_column_usage AS target_columns
    ON target_columns.constraint_catalog = referential_constraints.unique_constraint_catalog
    AND target_columns.constraint_schema = referential_constraints.unique_constraint_schema
    AND target_columns.constraint_name = referential_constraints.unique_constraint_name
    AND target_columns.ordinal_position = source_columns.position_in_unique_constraint
WHERE source_columns.table_schema = 'public'
ORDER BY source_columns.table_schema, source_columns.table_name, source_columns.ordinal_position;
"""

GET_INDEXES_QUERY = """
SELECT
    indexes.tablename AS table_name,
    indexes.indexname AS index_name,
    indexes.indexdef AS index_definition
FROM pg_indexes AS indexes
JOIN pg_catalog.pg_namespace AS namespaces
    ON namespaces.nspname = indexes.schemaname
WHERE indexes.schemaname = 'public'
ORDER BY indexes.schemaname, indexes.tablename, indexes.indexname;
"""
