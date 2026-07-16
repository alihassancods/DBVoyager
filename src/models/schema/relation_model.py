"""Database relationship metadata models."""

from pydantic import BaseModel, ConfigDict


class RelationInfo(BaseModel):
    """A parent-to-child relationship between database tables."""

    model_config = ConfigDict(from_attributes=True)

    parent_table: str
    parent_column: str
    child_table: str
    child_column: str
