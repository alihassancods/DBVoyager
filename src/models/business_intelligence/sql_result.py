from pydantic import BaseModel # type: ignore


class SQLResult(BaseModel):
    sql: str
    rows: list[dict]