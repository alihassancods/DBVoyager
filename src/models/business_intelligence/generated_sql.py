from pydantic import BaseModel # type: ignore


class GeneratedSQL(BaseModel):
    """
    Generated BI SQL query.
    """

    sql: str