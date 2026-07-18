"""Validated KPI workflow data."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


Aggregation = Literal["sum", "count", "avg", "min", "max"]
TimeGrain = Literal["day", "week", "month", "quarter", "year"]


class KPICandidate(BaseModel):
    schema_name: str = "public"
    table_name: str
    measure_column: str | None = None
    aggregation: Aggregation
    time_column: str | None = None
    dimension_column: str | None = None
    time_grain: TimeGrain = "month"
    title: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=1000)
    confidence: float = Field(ge=0, le=1)

    @field_validator("time_grain", mode="before")
    @classmethod
    def default_null_time_grain(cls, value: object) -> object:
        aliases = {"daily": "day", "weekly": "week", "monthly": "month", "quarterly": "quarter", "yearly": "year"}
        return aliases.get(str(value).lower(), str(value).lower()) if value is not None else "month"

    @field_validator("aggregation", mode="before")
    @classmethod
    def normalize_aggregation(cls, value: object) -> object:
        aliases = {"average": "avg", "mean": "avg", "count(*)": "count", "count_rows": "count"}
        return aliases.get(str(value).lower(), str(value).lower())

    @model_validator(mode="after")
    def count_when_no_measure_exists(self) -> "KPICandidate":
        if self.measure_column is None:
            self.aggregation = "count"
        return self


class KPIDefinition(KPICandidate):
    id: str
    monitored_database_id: str
    schema_revision_id: str
    max_points: int = Field(default=500, ge=1, le=1000)


class KPISnapshot(BaseModel):
    kpi_definition_id: str
    monitored_database_id: str
    analysis_run_id: str | None = None
    sql: str
    points: list[dict[str, object]]
    execution_ms: float
