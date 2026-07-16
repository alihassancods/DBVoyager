"""Database key metadata models."""

from pydantic import BaseModel, ConfigDict


class PrimaryKeyInfo(BaseModel):
    """A column participating in a table primary key."""

    model_config = ConfigDict(from_attributes=True)

    table_name: str
    column_name: str


class ForeignKeyInfo(BaseModel):
    """A foreign-key column reference between two tables."""

    model_config = ConfigDict(from_attributes=True)

    source_table: str
    source_column: str
    target_table: str
    target_column: str
