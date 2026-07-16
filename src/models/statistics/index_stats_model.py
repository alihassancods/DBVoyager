"""This one is the one that will track how the index are being used in the data bases"""

from pydantic import BaseModel, Field # type: ignore

class IndexStats(BaseModel):
    """
    Statistics about an index.
    """

    table_name: str
    index_name: str

    idx_scan: int = Field(
        ge=0,
        description="Times index used" # how many times the index was used to scan the table
    )

    idx_tup_read: int = Field(
        ge=0,
        description="Index entries read" # how many times the index was used to read entries from the table
    )

    idx_tup_fetch: int = Field(
        ge=0,
        description="Rows fetched through index" # how many times the index was used to fetch rows from the table
    )