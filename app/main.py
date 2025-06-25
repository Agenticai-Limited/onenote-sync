from fastapi import FastAPI
from contextlib import asynccontextmanager
from loguru import logger

from app.core.logger import setup_logging
from app.api.v1.router import api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup logging on startup
    setup_logging()
    logger.info("--- Starting Application ---")
    yield
    logger.info("--- Shutting Down Application ---")

app = FastAPI(
    title="OneNote Sync Pipeline",
    description="An API to process OneNote pages and sync them to Vector Database.",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(api_router, prefix="/api/v1")

@app.get("/", tags=["Health Check"])
async def read_root():
    return {"status": "ok"} 