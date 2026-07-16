"""Database index metadata models."""

from pydantic import BaseModel, ConfigDict


class IndexInfo(BaseModel):
    """Metadata describing a database index."""

    model_config = ConfigDict(from_attributes=True)

    table_name: str
    index_name: str
    index_definition: str
    indexed_columns: list[str]
    is_unique: bool
