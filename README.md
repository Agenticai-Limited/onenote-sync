# OneNote Sync Pipeline

A pipeline to process OneNote pages and store them in VectorDB.

## Features

- **OneNote Integration**: Fetches pages from Microsoft OneNote (including SharePoint OneNote).
- **Content Processing**: Extracts and processes content from OneNote pages.
- **VectorDB Storage**: Stores processed content as vectors in VectorDB.
- **PostgreSQL Metadata**: Stores page metadata in PostgreSQL for incremental updates.
- **Image & Table**: Supports image and table summary extraction.
- **FastAPI Interface**: Provides a RESTful API to trigger the pipeline.

## Project Structure

```
.env.example
app/
├── api/
│   └── v1/
│       ├── endpoints/ # API endpoints (e.g., pipeline)
│       └── router.py  # API router for v1
├── core/    # Core configurations, logging, and security
├── schemas/ # Pydantic models for data validation
├── services/ # Business logic (e.g., MS Graph auth, OneNote fetching, content processing, pipeline execution)
└── storage/ # Database handlers (PostgreSQL, Milvus)
main.py      # Main FastAPI application entry point
pyproject.toml # Project dependencies and metadata
run.sh       # Script to run the application
stop.sh      # Script to stop the application
uv.lock      # UV lock file for dependencies
```

## Setup

### Prerequisites

- Python 3.9+
- Milvus instance (running and accessible)
- PostgreSQL instance (running and accessible)

### 1. Environment Variables

Create a `.env` file in the root directory based on `.env.example` and fill in the required values:

```ini:.env
# Microsoft Graph API Settings
MS_CLIENT_ID="YOUR_MS_CLIENT_ID"
MS_CLIENT_SECRET="YOUR_MS_CLIENT_SECRET"

# SharePoint Settings
SHAREPOINT_SITE_NAME="YOUR_SHAREPOINT_SITE_NAME" # e.g., "My SharePoint Site"
SHAREPOINT_NOTEBOOK_NAME="YOUR_SHAREPOINT_NOTEBOOK_NAME" # e.g., "My OneNote Notebook"

# API Key for pipeline trigger endpoint
API_KEY="your_secret_api_key"
```

### 2. Install Dependencies

This project uses `uv` for dependency management.

```bash
uv sync
```

## Docker Setup

You can run this project with Docker for quick integration.

### 1. Build the image

In the project root directory:

```bash
docker build -t onenote-sync .
```

### 2. Run the container

Make sure to provide your `.env` file for environment variables:

```bash
docker run -d \
  --name onenote-sync \
  -p 52001:52001 \
  --env-file .env \
  onenote-sync
```

## Usage

The main API endpoint to trigger the OneNote processing pipeline is:

- **POST `/api/v1/pipeline/process-onenote`**

This endpoint requires an `X-API-KEY` header for authentication. The API key is configured in your `.env` file.

### Example using `curl`

The pipeline can fetch pages from either personal OneNote or SharePoint OneNote. By default, it uses SharePoint OneNote.
This behavior is controlled by the `use_sharepoint` boolean parameter in the request body, which is optional.

To use SharePoint OneNote (default behavior, `use_sharepoint` is implicitly `true`):

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/pipeline/process-onenote" \
     -H "X-API-KEY: your_secret_api_key" \
     # No -d parameter needed for default behavior
```

To explicitly use SharePoint OneNote (or if you prefer to be explicit):

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/pipeline/process-onenote" \
     -H "X-API-KEY: your_secret_api_key" \
     -H "Content-Type: application/json" \
     -d '{"use_sharepoint": true}'
```

To use personal OneNote (set `use_sharepoint` to `false`):

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/pipeline/process-onenote" \
     -H "X-API-KEY: your_secret_api_key" \
     -H "Content-Type: application/json" \
     -d '{"use_sharepoint": false}'
```

### Expected Response

Upon successful execution, the API will return a JSON object with the pipeline status, including counts and titles of new, updated, and skipped pages.

```json
{
  "status": "success",
  "message": null,
  "new_pages_count": 5,
  "new_pages_titles": ["Page Title 1", "Page Title 2"],
  "updated_pages_count": 2,
  "updated_pages_titles": ["Updated Page 1", "Updated Page 2"],
  "deleted_pages_count": 1,
  "deleted_pages_ids": ["0-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"],
  "skipped_pages_count": 10
}
```

## Sync Log Endpoints

The API provides endpoints to retrieve synchronization logs. These also require the `X-API-KEY` header.

### Get Logs by Run ID

- **GET `/api/v1/pipeline/logs/run/{sync_run_id}`**

Retrieves a summary and detailed logs for a specific synchronization run. The `sync_run_id` is the date of the run in `YYYYMMDD` format.

#### Example using `curl`

```bash
curl -X GET "http://127.0.0.1:8000/api/v1/pipeline/logs/run/20240712" \
     -H "X-API-KEY: your_secret_api_key"
```

#### Expected Response

```json
{
  "sync_run_id": "20240712",
  "summary": {
    "created": 1,
    "updated": 5,
    "deleted": 0,
    "total": 6
  },
  "logs": [
    {
      "log_id": 1,
      "sync_run_id": "20240712",
      "page_id": "0-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      "action_type": "UPDATED",
      "log_timestamp": "2024-07-12T10:30:00.123Z"
    }
  ]
}
```

### Get History by Page ID

- **GET `/api/v1/pipeline/logs/page/{page_id}`**

Retrieves the full synchronization history for a specific OneNote page.

#### Example using `curl`

```bash
curl -X GET "http://127.0.0.1:8000/api/v1/pipeline/logs/page/0-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
     -H "X-API-KEY: your_secret_api_key"
```

#### Expected Response

```json
{
  "page_id": "0-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "history": [
    {
      "log_id": 1,
      "sync_run_id": "20240712",
      "page_id": "0-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      "action_type": "UPDATED",
      "log_timestamp": "2024-07-12T10:30:00.123Z"
    },
    {
      "log_id": 2,
      "sync_run_id": "20240711",
      "page_id": "0-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      "action_type": "CREATED",
      "log_timestamp": "2024-07-11T08:00:00.456Z"
    }
  ]
}
```

## Logging

Application logs are configured using `loguru` and will be written to the `logs/` directory (`app.log` and `app-debug.log`).
