"""DBVoyager's HTTP application."""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI  # type: ignore
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

# Imports
from src.agent.business_intelligence.orchestrator import (
    BusinessIntelligenceOrchestrator,
)
from src.db_engine.connection import get_connection
from src.services.health.fix_service import HealthFixEngine

from .analysis_repository import claim_due_collection_runs, run_scheduled_collection
from .auth import router as auth_router
from .business_api import router as business_router
from .connections import router as connections_router
from .dashboard import router as dashboard_router
from .health_router import router as health_router
from .kpis import router as kpis_router
from .management import router as management_router
from .notifications import notification_listener, router as notifications_router
from .optimizer import router as optimizer_router
from .analysis_repository import claim_due_collection_runs, run_scheduled_collection
from .persistence_worker import process_persistence_jobs
from .query_generator import router as query_generator_router


def _interval_seconds(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async def scheduled_worker() -> None:
        while True:
            try:
                runs = await asyncio.to_thread(claim_due_collection_runs, 10)
                for run_id, connection_id, collection_kind in runs:
                    asyncio.create_task(
                        asyncio.to_thread(
                            run_scheduled_collection, run_id, connection_id, collection_kind
                        )
                    )
            except Exception:
                pass
            await asyncio.sleep(30)

    async def persistence_worker() -> None:
        while True:
            try:
                await asyncio.to_thread(process_persistence_jobs)
            except Exception:
                pass
            await asyncio.sleep(0.1)

    async def health_fix_engine_worker() -> None:
        # Check every hour (3600 seconds)
        CHECK_INTERVAL_SECONDS = 3600
        engine = HealthFixEngine()
        while True:
            try:
                await asyncio.to_thread(engine.run_automated_health_scan)
            except Exception:
                pass
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    # Automated Business Intelligence (BI) Loop
    async def bi_agent_worker() -> None:
        interval_seconds = _interval_seconds("DBVOYAGER_AGENT_INTERVAL_SECONDS", 1800)
        orchestrator = BusinessIntelligenceOrchestrator(
            connection_provider=lambda: get_connection()
        )
        while True:
            try:
                question = "Which product category generates the highest revenue?"
                # Run the BI investigation non-blockingly in thread pool
                await asyncio.to_thread(orchestrator.investigate, question=question)
            except Exception:
                pass
            await asyncio.sleep(interval_seconds)

    # Initialize task references
    task = asyncio.create_task(scheduled_worker())
    persistence_task = asyncio.create_task(persistence_worker())
    notifications_task = asyncio.create_task(notification_listener())
    bi_agent_task = asyncio.create_task(bi_agent_worker())
    try:
        yield
    finally:
        # Clean shutdown for all workers
        task.cancel()
        persistence_task.cancel()
        notifications_task.cancel()
        bi_agent_task.cancel()
        await asyncio.gather(task, persistence_task, notifications_task, bi_agent_task, return_exceptions=True)

app = FastAPI(
    title="DBVoyager API",
    description="AI-powered PostgreSQL investigation platform",
    version="1.0.0",
    lifespan=lifespan,
)

origins = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]
local_origin_pattern = r".*"
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=os.getenv("FRONTEND_ORIGIN_REGEX", local_origin_pattern),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["set-auth-jwt"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


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
app.include_router(business_router)
app.include_router(management_router)
app.include_router(notifications_router)
app.include_router(query_generator_router)
