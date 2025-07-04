import psycopg2
from psycopg2.extras import RealDictCursor
from pymilvus import (
    connections, utility, Collection, FieldSchema, CollectionSchema, DataType
)
from typing import List, Dict, Optional, Any
from datetime import datetime

from app.core.config import settings
from loguru import logger

class PostgresHandler:
    """
    Handles all interactions with the PostgreSQL database.
    """
    def __init__(self):
        self.conn = None
        try:
            logger.info(f"Connecting to PostgreSQL database '{settings.POSTGRES_DB}' at {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}...")
            self.conn = psycopg2.connect(
                dbname=settings.POSTGRES_DB,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                host=settings.POSTGRES_HOST,
                port=settings.POSTGRES_PORT
            )
            logger.info("PostgreSQL connection successful.")
        except psycopg2.OperationalError as e:
            logger.error(f"Could not connect to PostgreSQL database: {e}")
            raise

    def setup_database(self):
        """
        Creates the 'onenote_pages_metadata' table if it does not already exist.
        """
        create_table_query = """
        CREATE TABLE IF NOT EXISTS onenote_pages_metadata (
            page_id TEXT PRIMARY KEY,
            last_modified_time TIMESTAMP WITH TIME ZONE,
            title TEXT,
            section_name TEXT
        );
        """
        # Also create the authorizations table if it doesn't exist.
        # This part was missing from the original logic but is necessary for auth to work.
        create_auth_table_query = """
        CREATE TABLE IF NOT EXISTS onenote_authorizations (
            microsoft_user_id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            access_token TEXT,
            refresh_token TEXT,
            token_expires_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
        with self.conn.cursor() as cur:
            cur.execute(create_table_query)
            cur.execute(create_auth_table_query)
        self.conn.commit()
        logger.info("Database setup complete. Tables are ready.")

    def get_page_last_modified(self, page_id: str) -> Optional[datetime]:
        """
        Retrieves the last modified timestamp for a given page_id.

        Returns:
            A datetime object or None if the page is not found.
        """
        query = "SELECT last_modified_time FROM onenote_pages_metadata WHERE page_id = %s;"
        with self.conn.cursor() as cur:
            cur.execute(query, (page_id,))
            result = cur.fetchone()
            if result:
                return result[0]
            return None

    def upsert_page_metadata(self, page_id: str, last_modified_time: str, title: str, section_name: str):
        """
        Inserts a new page's metadata or updates it if the page_id already exists.
        The last_modified_time should be an ISO 8601 string.
        """
        query = """
        INSERT INTO onenote_pages_metadata (page_id, last_modified_time, title, section_name)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (page_id) DO UPDATE SET
            last_modified_time = EXCLUDED.last_modified_time,
            title = EXCLUDED.title,
            section_name = EXCLUDED.section_name;
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (page_id, last_modified_time, title, section_name))
        self.conn.commit()
        logger.debug(f"Upserted metadata for page: {title}")

    def get_auth_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves authorization details for a given email.

        Returns:
            A dictionary with auth details or None if not found.
        """
        query = "SELECT microsoft_user_id, email, access_token, refresh_token, token_expires_at FROM onenote_authorizations WHERE email = %s;"
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (email,))
            result = cur.fetchone()
            return result

    def update_auth_tokens(self, email: str, access_token: str, refresh_token: str, token_expires_at: datetime):
        """
        Updates the tokens and their expiry for a given user.
        """
        query = """
        UPDATE onenote_authorizations SET
            access_token = %s,
            refresh_token = %s,
            token_expires_at = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE email = %s;
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (access_token, refresh_token, token_expires_at, email))
        self.conn.commit()
        logger.info(f"Updated auth tokens for user: {email}")

    def close(self):
        """Closes the database connection."""
        if self.conn:
            self.conn.close()
            logger.info("PostgreSQL connection closed.")


class MilvusHandler:
    """
    Handles all interactions with the Milvus vector database.
    """
    def __init__(self):
        self.collection_name = settings.MILVUS_COLLECTION_NAME
        try:
            # Connect to Milvus
            logger.info(f"Connecting to Milvus at {settings.MILVUS_HOST}:{settings.MILVUS_PORT}...")
            connections.connect("default", host=settings.MILVUS_HOST, port=str(settings.MILVUS_PORT))
            logger.info("Milvus connection successful.")
            self.collection = None
        except Exception as e:
            logger.error(f"Could not connect to Milvus: {e}")
            raise

    def create_collection_if_not_exists(self):
        """
        Creates the Milvus collection with the defined schema if it doesn't exist.
        """
        if utility.has_collection(self.collection_name):
            logger.info(f"Milvus collection '{self.collection_name}' already exists.")
            self.collection = Collection(self.collection_name)
            self.collection.load() # Load collection into memory
            return

        logger.info(f"Milvus collection '{self.collection_name}' not found. Creating...")
        fields = [
            FieldSchema(name="chunk_id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=1024),
            FieldSchema(name="page_id", dtype=DataType.VARCHAR, max_length=255),
            FieldSchema(name="text_content", dtype=DataType.VARCHAR, max_length=4096),
            FieldSchema(name="page_title", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="section_name", dtype=DataType.VARCHAR, max_length=512)
        ]
        schema = CollectionSchema(fields, description="OneNote page chunks", enable_dynamic_field=False)
        self.collection = Collection(name=self.collection_name, schema=schema)
        
        # Create an index for the vector field
        index_params = {
            "metric_type": "IP",
            "index_type": "AUTOINDEX",
        }
        self.collection.create_index(field_name="vector", index_params=index_params)
        logger.info(f"Successfully created collection '{self.collection_name}' and index.")
        self.collection.load() # Load collection into memory
        logger.info(f"Collection '{self.collection_name}' loaded into memory.")


    def delete_vectors_by_page_id(self, page_id: str):
        """
        Deletes all vectors/chunks associated with a specific page_id.
        """
        if not self.collection:
            self.collection = Collection(self.collection_name)
            
        expr = f"page_id == '{page_id}'"
        self.collection.delete(expr)
        logger.info(f"Deleted vectors from Milvus for page_id: {page_id}")

    def insert_chunks(self, chunks: List[Dict[str, Any]]):
        """
        Inserts a list of processed chunks into the Milvus collection.
        """
        if not chunks:
            logger.info("No chunks to insert.")
            return
            
        if not self.collection:
            self.collection = Collection(self.collection_name)
            
        # Prepare data for insertion (column-based)
        data = [[] for _ in self.collection.schema.fields if not _.is_primary]
        field_names = [field.name for field in self.collection.schema.fields if not field.is_primary]

        for chunk in chunks:
            for i, name in enumerate(field_names):
                data[i].append(chunk[name])

        self.collection.insert(data)
        self.collection.flush()
        logger.info(f"Inserted {len(chunks)} chunks into Milvus collection '{self.collection_name}'.")

    def close(self):
        """Closes the Milvus connection."""
        alias = "default"
        if connections.has_connection(alias):
            connections.disconnect(alias)
            logger.info("Milvus connection closed.") 