"""Database table metadata models."""

from pydantic import BaseModel, ConfigDict


class TableInfo(BaseModel):
    """Metadata describing a database table."""

    model_config = ConfigDict(from_attributes=True)

    table_name: str
    schema_name: str
    table_type: str
    estimated_rows: int | None
