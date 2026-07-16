"""Database column metadata models."""

from pydantic import BaseModel, ConfigDict


class ColumnInfo(BaseModel):
    """Metadata describing a database table column."""

    model_config = ConfigDict(from_attributes=True)

    table_name: str
    column_name: str
    data_type: str
    is_nullable: bool
    column_default: str | None
    ordinal_position: int
