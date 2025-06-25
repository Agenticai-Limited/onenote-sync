from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Load settings from a .env file
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Microsoft Graph API
    MS_CLIENT_ID: str
    MS_CLIENT_SECRET: str
    MS_USER_EMAIL: str
    MS_TOKEN_URL: str = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    MS_GRAPH_SCOPE: str = "Notes.Read.All offline_access"

    # AWS Bedrock
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION_NAME: str 
    EMBEDDING_MODEL_ID: str 
  
    # Milvus
    MILVUS_HOST: str 
    MILVUS_PORT: int 
    MILVUS_COLLECTION_NAME: str

    # PostgreSQL
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_DB: str
    
    # Local Data Storage
    IMAGE_STORAGE_PATH: str

    # API Security
    API_KEY: str

# Create a single settings instance to be used across the application
settings = Settings()

# Note: The logic for creating the IMAGE_STORAGE_PATH directory has been moved.
