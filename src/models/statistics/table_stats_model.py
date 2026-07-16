"""This one will store the info about the table in the data bases"""

from pydantic import BaseModel, Field # type: ignore

class TableStats(BaseModel):
    """
    Statistics for a table.
    """

    table_name: str

    seq_scan: int = Field(
        ge=0,
        description="Sequential scans" # how many times the table was scanned sequentially
    )

    idx_scan: int = Field(
        ge=0,
        description="Index scans" # how many times the table was scanned using an index
    )

    n_live_tup: int = Field(
        ge=0,
        description="Live rows" # the number of the useable rows in the table
    )

    n_dead_tup: int = Field(
        ge=0,
        description="Dead rows" # the number of the dead rows in the table
    )