"""Aggregate database schema metadata model."""

from pydantic import BaseModel, ConfigDict #type: ignore

from .column_model import ColumnInfo
from ...db_engine.inspectors.index_model import IndexInfo
from .key_model import ForeignKeyInfo, PrimaryKeyInfo
from .relation_model import RelationInfo
from .table_model import TableInfo


class DatabaseSchema(BaseModel):
    """The metadata collected for a database schema."""

    model_config = ConfigDict(from_attributes=True)

    tables: list[TableInfo]
    columns: list[ColumnInfo]
    primary_keys: list[PrimaryKeyInfo]
    foreign_keys: list[ForeignKeyInfo]
    relations: list[RelationInfo]
    indexes: list[IndexInfo]
