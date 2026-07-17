from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict
from src.agent.business_intelligence.orchestrator import BusinessIntelligenceOrchestrator
from src.db_engine.connection import get_connection 

router = APIRouter(prefix="/business", tags=["Business Intelligence"])

# Clean, user-facing request model
class InvestigationRequest(BaseModel):
    question: str
    # Highlight: Changed type to dict and defaulted to an empty dictionary
    schema_context: Dict[str, Any] = Field(default_factory=dict)

@router.post("/investigate")
async def investigate_business_question(request: InvestigationRequest) -> dict[str, Any]:
    """
    Executes the full BI investigation workflow.
    """
    try:
        orchestrator = BusinessIntelligenceOrchestrator(
            connection_provider=get_connection
        )

        # Execute the investigation using the dictionary passed safely inside request
        result = orchestrator.investigate(
            question=request.question,
            schema_context=request.schema_context  # This will now always be a valid dict object!
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"BI Investigation failed: {str(e)}")