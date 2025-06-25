from datetime import datetime
from loguru import logger

from app.services import ms_graph_auth, onenote_fetcher
from app.services.content_processor import ContentProcessor
from app.storage.db_handler import PostgresHandler, MilvusHandler
from app.core.config import settings

def run_pipeline():
    """
    Executes the full OneNote data ingestion and processing pipeline.
    """
    logger.info("Starting OneNote processing pipeline...")
    pg_handler = None
    milvus_handler = None

    try:
        # 1. Initialize handlers
        pg_handler = PostgresHandler()
        milvus_handler = MilvusHandler()
        content_processor = ContentProcessor()

        # 2. Setup databases
        pg_handler.setup_database()
        milvus_handler.create_collection_if_not_exists()

        # 3. Get Access Token
        logger.info("Getting Microsoft Graph access token...")
        # Note: In a multi-user system, the email should not be hardcoded.
        # This is a good place for future improvement.
        access_token = ms_graph_auth.get_access_token(user_email=settings.MS_USER_EMAIL)

        # 4. Fetch all pages from OneNote
        logger.info("Fetching all pages from OneNote...")
        all_pages = onenote_fetcher.fetch_all_pages(access_token)
        if not all_pages:
            logger.warning("No pages found or fetching failed. Stopping pipeline.")
            return {
                "status": "success",
                "message": "No pages found or fetching failed.",
                "new_pages_count": 0, "new_pages_titles": [],
                "updated_pages_count": 0, "updated_pages_titles": [],
                "skipped_pages_count": 0
            }

        # 5. Process pages with incremental updates
        process_stats = {
            "new": {"count": 0, "titles": []},
            "updated": {"count": 0, "titles": []},
            "skipped": {"count": 0}
        }
        for page in all_pages:
            page_id = page['id']
            page_title = page['title']
            # OneNote provides ISO 8601 UTC time (e.g., '2024-05-22T05:39:09.33Z')
            onenote_modified_time_str = page['lastModifiedDateTime']
            onenote_modified_time = datetime.fromisoformat(onenote_modified_time_str.replace('Z', '+00:00'))

            db_modified_time = pg_handler.get_page_last_modified(page_id)

            if not db_modified_time or onenote_modified_time > db_modified_time:
                if not db_modified_time:
                    process_stats["new"]["count"] += 1
                    process_stats["new"]["titles"].append(page_title)
                    logger.info(f"Processing new page: ('{page_title}') {page_id}")
                else:
                    process_stats["updated"]["count"] += 1
                    process_stats["updated"]["titles"].append(page_title)
                    logger.info(f"Processing updated page: ('{page_title}') {page_id}")

                milvus_handler.delete_vectors_by_page_id(page_id)
                chunks = content_processor.process_page(page, access_token)
                if chunks:
                    milvus_handler.insert_chunks(chunks)
                pg_handler.upsert_page_metadata(
                    page_id=page_id,
                    last_modified_time=onenote_modified_time.isoformat(),
                    title=page_title,
                    section_name=page.get('sectionDisplayName', '')
                )
            else:
                process_stats["skipped"]["count"] += 1
                logger.debug(f"Skipping unchanged page: {page_id} ('{page_title}')")

        logger.info(f"Pipeline finished. New: {process_stats['new']['count']}, Updated: {process_stats['updated']['count']}, Skipped: {process_stats['skipped']['count']}.")
        return {
            "status": "success",
            "new_pages_count": process_stats["new"]["count"],
            "new_pages_titles": process_stats["new"]["titles"],
            "updated_pages_count": process_stats["updated"]["count"],
            "updated_pages_titles": process_stats["updated"]["titles"],
            "skipped_pages_count": process_stats["skipped"]["count"],
        }
    finally:
        # 6. Close connections
        if pg_handler:
            pg_handler.close()
        if milvus_handler:
            milvus_handler.close()
        logger.info("Database connections closed.") 
