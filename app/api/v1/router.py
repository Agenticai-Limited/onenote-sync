from fastapi import APIRouter
from app.api.v1.endpoints import pipeline

api_router = APIRouter()
api_router.include_router(pipeline.router, prefix="/pipeline", tags=["Pipeline"]) 