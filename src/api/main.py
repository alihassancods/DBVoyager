"""DBVoyager's HTTP application."""

from fastapi import FastAPI #type: ignore

from .auth import router as auth_router
from .connections import router as connections_router
from .dashboard import router as dashboard_router
from .kpis import router as kpis_router
from .optimizer import router as optimizer_router


app = FastAPI(
    title="DBVoyager API",
    description="AI-powered PostgreSQL investigation platform",
    version="1.0.0",
)

@app.get("/")
async def root():
    return {"message": "Welcome to DBVoyager API!"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

app.include_router(connections_router)
app.include_router(dashboard_router)
app.include_router(kpis_router)
app.include_router(optimizer_router)
app.include_router(auth_router)
