"""Inspector for PostgreSQL index metadata."""

import logging
import re
from collections.abc import Callable, Mapping
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from src.db_engine.queries.schema_queries import GET_INDEXES_QUERY
from .index_model import IndexInfo

ConnectionProvider = Callable[[], Any]
_UNIQUE_INDEX_PATTERN = re.compile(r"\bCREATE\s+UNIQUE\s+INDEX\b", re.IGNORECASE)
_USING_PATTERN = re.compile(r"\bUSING\s+\S+\s*\(", re.IGNORECASE)


class IndexInspector:
    """Collect and parse PostgreSQL index metadata."""

    def __init__(self, connection_provider: ConnectionProvider) -> None:
        self._connection_provider = connection_provider
        self._logger = logging.getLogger(__name__)

    def get_indexes(self) -> list[IndexInfo]:
        """Return parsed metadata for indexes in user-visible schemas."""
        connection = None
        try:
            connection = self._connection_provider()
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(GET_INDEXES_QUERY)
                rows = cursor.fetchall()
            return [self._to_index_info(row) for row in rows]
        except psycopg2.Error:
            self._logger.exception("Failed to inspect database indexes")
            return []
        except (KeyError, TypeError, ValueError):
            self._logger.exception("Invalid index metadata returned by the database")
            return []
        finally:
            if connection is not None:
                connection.close()

    def _to_index_info(self, row: Mapping[str, Any]) -> IndexInfo:
        data = dict(row)
        definition = str(data["index_definition"])
        return IndexInfo(
            table_name=data["table_name"],
            index_name=data["index_name"],
            index_definition=definition,
            indexed_columns=self._extract_indexed_columns(definition),
            is_unique=bool(_UNIQUE_INDEX_PATTERN.search(definition)),
        )

    def _extract_indexed_columns(self, definition: str) -> list[str]:
        match = _USING_PATTERN.search(definition)
        if match is None:
            self._logger.warning("Unable to parse index definition: %s", definition)
            return []

        start = match.end() - 1
        end = self._find_closing_parenthesis(definition, start)
        if end is None:
            self._logger.warning("Malformed index definition: %s", definition)
            return []

        return self._split_columns(definition[start + 1 : end])

    @staticmethod
    def _find_closing_parenthesis(value: str, start: int) -> int | None:
        depth = 0
        in_quotes = False
        for position, character in enumerate(value[start:], start=start):
            if character == '"':
                in_quotes = not in_quotes
            elif not in_quotes and character == "(":
                depth += 1
            elif not in_quotes and character == ")":
                depth -= 1
                if depth == 0:
                    return position
        return None

    @staticmethod
    def _split_columns(value: str) -> list[str]:
        columns: list[str] = []
        depth = 0
        in_quotes = False
        start = 0
        for position, character in enumerate(value):
            if character == '"':
                in_quotes = not in_quotes
            elif not in_quotes and character == "(":
                depth += 1
            elif not in_quotes and character == ")":
                depth -= 1
            elif character == "," and not in_quotes and depth == 0:
                columns.append(value[start:position].strip())
                start = position + 1
        columns.append(value[start:].strip())
        return [column for column in columns if column]
