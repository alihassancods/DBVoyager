"""Transformation of foreign-key metadata into table relationships."""

from src.models.schema.key_model import ForeignKeyInfo
from src.models.schema.relation_model import RelationInfo


class RelationInspector:
    """Build relationship metadata from foreign-key definitions."""

    def build_relations(self, foreign_keys: list[ForeignKeyInfo]) -> list[RelationInfo]:
        """Map each foreign key to a parent-to-child relationship."""
        return [
            RelationInfo(
                parent_table=foreign_key.target_table,
                parent_column=foreign_key.target_column,
                child_table=foreign_key.source_table,
                child_column=foreign_key.source_column,
            )
            for foreign_key in foreign_keys
        ]
