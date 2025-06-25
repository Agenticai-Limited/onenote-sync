from fastapi import APIRouter, HTTPException, Depends
from loguru import logger

from app.services import pipeline_service
from app.schemas.pipeline_status import PipelineStatus
from app.core.security import verify_api_key
from datetime import datetime

router = APIRouter()

@router.post(
    "/process-onenote",
    response_model=PipelineStatus,
    status_code=200,
    dependencies=[Depends(verify_api_key)]
)
def trigger_pipeline():
    """
    Triggers the OneNote processing pipeline and waits for it to complete,
    returning a detailed status of the operation.
    Requires a valid API Key in the 'X-API-KEY' header.
    
    """
    try:
        logger.info("Starting pipeline processing...")
        timenow = datetime.now()
        result = pipeline_service.run_pipeline()
        logger.info(f"Pipeline processing finished successfully. Took {(datetime.now() - timenow).total_seconds():.2f} seconds")
        return result
    except Exception as e:
        logger.exception(f"An error occurred during the pipeline execution: {e}")
        # Re-raising as HTTPException to let FastAPI handle the error response
        raise HTTPException(
            status_code=500,
            detail="An internal server error occurred during pipeline execution."
        ) 
