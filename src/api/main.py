"""DBVoyager's HTTP application."""

from fastapi import FastAPI

from .connections import router as connections_router
from .dashboard import router as dashboard_router
from .store import _connections


app = FastAPI(title="DBVoyager API")
app.include_router(connections_router)
app.include_router(dashboard_router)
