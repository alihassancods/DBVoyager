from pydantic import BaseModel
from src.models.schema.schema_model import DatabaseSchema
from src.models.business_intelligence.investigation_plan import InvestigationPlan


class SQLRequest(BaseModel):

    question: str

    schema_context: DatabaseSchema

    plan: InvestigationPlan

    sql: str