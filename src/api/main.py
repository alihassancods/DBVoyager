"""DBVoyager's HTTP application."""

import os

from fastapi import FastAPI #type: ignore
from fastapi.middleware.cors import CORSMiddleware

from .auth import router as auth_router
from .connections import router as connections_router
from .dashboard import router as dashboard_router
from .kpis import router as kpis_router
from .optimizer import router as optimizer_router
from .business_api import router as business_router # Import the new router
from .management import router as management_router

app = FastAPI(
    title="DBVoyager API",
    description="AI-powered PostgreSQL investigation platform",
    version="1.0.0",
)

origins = [origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["set-auth-jwt"],
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
app.include_router(business_router) # Include it here
app.include_router(management_router)
