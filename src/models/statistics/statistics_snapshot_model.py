"""This will give the stats of all of them combined"""

from pydantic import BaseModel #type: ignore

from src.models.statistics.query_stats_model import QueryStats
from src.models.statistics.table_stats_model import TableStats
from src.models.statistics.index_stats_model import IndexStats
from src.models.statistics.lock_stats_model import LockStats
from src.models.statistics.database_stats_model import DatabaseStats


class StatisticsSnapshot(BaseModel):
    """
    Complete statistics snapshot.
    """

    query_stats: list[QueryStats]

    table_stats: list[TableStats]

    index_stats: list[IndexStats]

    lock_stats: list[LockStats]

    database_stats: DatabaseStats