from datetime import datetime
from loguru import logger

from app.services import ms_graph_auth, sharepoint_onenote_fetcher, onenote_fetcher
from app.services.content_processor import ContentProcessor
from app.storage.db_handler import PostgresHandler, MilvusHandler
from app.core.config import settings

def run_pipeline(use_sharepoint: bool = True):
    """
    Executes the full OneNote data ingestion and processing pipeline.
    """
    logger.info("Starting OneNote processing pipeline...")
    pg_handler = None
    milvus_handler = None
    sync_run_id = datetime.now().strftime("%Y%m%d")

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
        access_token = ms_graph_auth.get_access_token(user_email=settings.MS_USER_EMAIL)

        # 4. Fetch all pages from OneNote
        if use_sharepoint:
            logger.info("Fetching all pages from SharePoint OneNote...")
            all_pages = sharepoint_onenote_fetcher.fetch_all_pages_sharepoint(access_token)
        else:
            logger.info("Fetching all pages from OneNote...")
            all_pages = onenote_fetcher.fetch_all_pages(access_token)
        
        if not all_pages:
            logger.warning("No pages found or fetching failed. Stopping pipeline.")
            return {
                "status": "success",
                "message": "No pages found or fetching failed.",
                "new_pages_count": 0, "new_pages_titles": [],
                "updated_pages_count": 0, "updated_pages_titles": [],
                "deleted_pages_count": 0, "deleted_pages_ids": [],
                "skipped_pages_count": 0
            }

        # 5. Process pages with incremental updates
        process_stats = {
            "new": {"count": 0, "titles": []},
            "updated": {"count": 0, "titles": []},
            "deleted": {"count": 0, "ids": []},
            "skipped": {"count": 0}
        }
        
        remote_page_ids = {page['id'] for page in all_pages}

        for page in all_pages:
            page_id = page['id']
            page_title = page['title']
            onenote_modified_time_str = page['lastModifiedDateTime']
            onenote_modified_time = datetime.fromisoformat(onenote_modified_time_str.replace('Z', '+00:00'))
            db_modified_time = pg_handler.get_page_last_modified(page_id)

            if not db_modified_time:
                process_stats["new"]["count"] += 1
                process_stats["new"]["titles"].append(page_title)
                logger.info(f"Processing new page: ('{page_title}') {page_id}")
                pg_handler.insert_sync_log(sync_run_id, page_id, 'CREATED')
                
                milvus_handler.delete_vectors_by_page_id(page_id)
                chunks = content_processor.process_page(page, access_token)
                if chunks:
                    milvus_handler.insert_chunks(chunks)
                pg_handler.upsert_page_metadata(
                    page_id=page_id,
                    last_modified_time=onenote_modified_time.isoformat(),
                    title=page_title,
                    section_name=page.get('sectionDisplayName', ''),
                )
            elif onenote_modified_time > db_modified_time:
                process_stats["updated"]["count"] += 1
                process_stats["updated"]["titles"].append(page_title)
                logger.info(f"Processing updated page: ('{page_title}') {page_id}")
                pg_handler.insert_sync_log(sync_run_id, page_id, 'UPDATED')

                milvus_handler.delete_vectors_by_page_id(page_id)
                chunks = content_processor.process_page(page, access_token)
                if chunks:
                    milvus_handler.insert_chunks(chunks)
                pg_handler.upsert_page_metadata(
                    page_id=page_id,
                    last_modified_time=onenote_modified_time.isoformat(),
                    title=page_title,
                    section_name=page.get('sectionDisplayName', ''),
                )
            else:
                process_stats["skipped"]["count"] += 1
                logger.debug(f"Skipping unchanged page: {page_id} ('{page_title}')")

        # 6. Detect and process deleted pages
        local_page_ids = set(pg_handler.get_all_page_ids())
        deleted_page_ids = local_page_ids - remote_page_ids
        
        if deleted_page_ids:
            logger.info(f"Detected {len(deleted_page_ids)} deleted pages.")
            for page_id in deleted_page_ids:
                process_stats["deleted"]["count"] += 1
                process_stats["deleted"]["ids"].append(page_id)
                logger.info(f"Processing deleted page: {page_id}")
                
                # Log deletion
                pg_handler.insert_sync_log(sync_run_id, page_id, 'DELETED')
                
                # Delete from Milvus and Postgres
                milvus_handler.delete_vectors_by_page_id(page_id)
                pg_handler.delete_page_metadata(page_id)
        
        logger.info(f"Pipeline finished. New: {process_stats['new']['count']}, Updated: {process_stats['updated']['count']}, "
                    f"Deleted: {process_stats['deleted']['count']}, Skipped: {process_stats['skipped']['count']}.")
        return {
            "status": "success",
            "new_pages_count": process_stats["new"]["count"],
            "new_pages_titles": process_stats["new"]["titles"],
            "updated_pages_count": process_stats["updated"]["count"],
            "updated_pages_titles": process_stats["updated"]["titles"],
            "deleted_pages_count": process_stats["deleted"]["count"],
            "deleted_pages_ids": process_stats["deleted"]["ids"],
            "skipped_pages_count": process_stats["skipped"]["count"],
        }
    finally:
        # 7. Close connections
        if pg_handler:
            pg_handler.close()
        if milvus_handler:
            milvus_handler.close()
        logger.info("Database connections closed.") 
