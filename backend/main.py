"""
AICT Backend — FastAPI application entry point.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.v1.router import api_router
from backend.api_internal.router import internal_router
from backend.core.error_handlers import aict_exception_handler
from backend.core.exceptions import AICTException
from backend.websocket.endpoint import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown


app = FastAPI(title="AICT Backend", version="0.1.0", lifespan=lifespan)

# CORS — allow all in development; tighten for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
app.add_exception_handler(AICTException, aict_exception_handler)

# Public API
app.include_router(api_router, prefix="/api/v1")

# Internal API (agent tools)
app.include_router(internal_router, prefix="/internal/agent")

# WebSocket endpoint
app.include_router(ws_router)
