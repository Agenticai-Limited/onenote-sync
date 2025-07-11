from pydantic import BaseModel
from typing import List

class PipelineStatus(BaseModel):
    status: str
    message: str | None = None
    new_pages_count: int
    new_pages_titles: List[str]
    updated_pages_count: int
    updated_pages_titles: List[str]
    deleted_pages_count: int
    deleted_pages_ids: List[str]
    skipped_pages_count: int 