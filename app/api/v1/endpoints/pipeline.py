from fastapi import APIRouter, HTTPException, Depends, Body
from loguru import logger
from pydantic import BaseModel
from typing import Optional

from app.services import pipeline_service
from app.schemas.pipeline_status import PipelineStatus
from app.core.security import verify_api_key
from datetime import datetime

# Define a request body model for the pipeline trigger
class PipelineTriggerRequest(BaseModel):
    use_sharepoint: bool = True # Default to SharePoint OneNote

router = APIRouter()

@router.post(
    "/process-onenote",
    response_model=PipelineStatus,
    status_code=200,
    dependencies=[Depends(verify_api_key)]
)
def trigger_pipeline(request: Optional[PipelineTriggerRequest] = Body(None)):
    """
    Triggers the OneNote processing pipeline and waits for it to complete,
    returning a detailed status of the operation.
    Requires a valid API Key in the 'X-API-KEY' header.
    
    Args:
        request (Optional[PipelineTriggerRequest]): Optional request body containing the `use_sharepoint` flag.
    """
    try:
        logger.info("Starting pipeline processing...")
        timenow = datetime.now()
        
        # Determine use_sharepoint based on request body, or use default
        use_sharepoint = True
        if request is not None:
            use_sharepoint = request.use_sharepoint

        result = pipeline_service.run_pipeline(use_sharepoint=use_sharepoint)
        logger.info(f"Pipeline processing finished successfully. Took {(datetime.now() - timenow).total_seconds():.2f} seconds")
        return result
    except Exception as e:
        logger.exception(f"An error occurred during the pipeline execution: {e}")
        # Re-raising as HTTPException to let FastAPI handle the error response
        raise HTTPException(
            status_code=500,
            detail="An internal server error occurred during pipeline execution."
        ) 
