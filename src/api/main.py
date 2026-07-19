"""DBVoyager's HTTP application."""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI #type: ignore
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .auth import router as auth_router
from .connections import router as connections_router
from .dashboard import router as dashboard_router
from .kpis import router as kpis_router
from .optimizer import router as optimizer_router
from .business_api import router as business_router # Import the new router
from .management import router as management_router
from .analysis_repository import claim_due_collection_runs, run_scheduled_collection
from .persistence_worker import process_persistence_jobs


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async def scheduled_worker() -> None:
        while True:
            try:
                runs = await asyncio.to_thread(claim_due_collection_runs, 10)
                for run_id, connection_id, collection_kind in runs:
                    asyncio.create_task(asyncio.to_thread(run_scheduled_collection, run_id, connection_id, collection_kind))
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

    task = asyncio.create_task(scheduled_worker())
    persistence_task = asyncio.create_task(persistence_worker())
    try:
        yield
    finally:
        task.cancel()
        persistence_task.cancel()
        await asyncio.gather(task, persistence_task, return_exceptions=True)

app = FastAPI(
    title="DBVoyager API",
    description="AI-powered PostgreSQL investigation platform",
    version="1.0.0",
    lifespan=lifespan,
)

origins = [origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
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
app.include_router(business_router) # Include it here
app.include_router(management_router)
