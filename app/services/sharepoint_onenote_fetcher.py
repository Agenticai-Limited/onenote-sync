from typing import List, Dict, Any
import requests
from requests.exceptions import RequestException
from loguru import logger
from app.core.config import settings

# Define your SharePoint Site ID and the specific OneNote Notebook ID
# These values were derived from our previous successful Graph API calls.
# Replace these with the actual IDs you obtained.
# SHAREPOINT_SITE_ID = "clientportal01.sharepoint.com,671534a4-9caf-4dbc-a183-4db67ae5b563,d102d1f5-8d39-48bb-a833-c692186599b2"
# TARGET_ONENOTE_NOTEBOOK_ID = "1-ef4525d6-91a0-47c3-91dd-20799513c68a"  # ID for "NZFC Customer Services Procedures & Policies"

def get_sharepoint_site_id(access_token: str) -> str:
    """
    Get the SharePoint site ID from the access token.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        response = requests.get(f"https://graph.microsoft.com/v1.0/sites?search={settings.SHAREPOINT_SITE_NAME}", headers=headers)
        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
        sites_data = response.json()
        for site in sites_data.get('value', []):
            # Use 'displayName' for user-friendly names
            if site.get('name') == settings.SHAREPOINT_SITE_NAME:
                logger.info(f"Found SharePoint site '{settings.SHAREPOINT_SITE_NAME}' with ID: {site['id']}")
                return site['id']
        # If loop finishes without finding the site
        raise ValueError(f"SharePoint site '{settings.SHAREPOINT_SITE_NAME}' not found in Graph API response.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching SharePoint site ID: {e}")
        raise

def get_sharepoint_notebook_id(access_token: str, sharepoint_site_id: str) -> str:
    """
    Get the SharePoint notebook ID from the access token.
    """
    notebooks_url = f"https://graph.microsoft.com/v1.0/sites/{sharepoint_site_id}/onenote/notebooks"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        response = requests.get(notebooks_url, headers=headers)
        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
        notebooks_data = response.json()
        
        for notebook in notebooks_data.get('value', []):
            if notebook.get('displayName') == settings.SHAREPOINT_NOTEBOOK_NAME:
                logger.info(f"Found OneNote notebook '{settings.SHAREPOINT_NOTEBOOK_NAME}' with ID: {notebook['id']}")
                return notebook['id']
        # If loop finishes without finding the notebook
        raise ValueError(f"OneNote notebook '{settings.SHAREPOINT_NOTEBOOK_NAME}' not found in site {sharepoint_site_id}.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching OneNote notebook ID: {e}")
        raise # Re-raise the exception after logging


def fetch_all_pages_sharepoint(access_token: str) -> List[Dict[str, Any]]:
    """
    Fetches all pages from a specific OneNote notebook in a SharePoint site.
    It gets sections, then pages per section, returning raw HTML content and metadata.

    Args:
        access_token: Microsoft Graph API access token.

    Returns:
        A list of page data dictionaries. Returns an empty list on failure.
    """
    headers = {"Authorization": f"Bearer {access_token}"}

    # Define your SharePoint Site ID and the specific OneNote Notebook ID
    # These values were derived from our previous successful Graph API calls.
    # Replace these with the actual IDs you obtained.
    sharepoint_site_id = get_sharepoint_site_id(access_token)
    target_onenote_notebook_id = get_sharepoint_notebook_id(access_token, sharepoint_site_id)

    if not sharepoint_site_id or not target_onenote_notebook_id:
        logger.error("Failed to obtain SharePoint site ID or OneNote notebook ID.")
        return []

    # SharePoint OneNote specific URLs
    # We now use the specific notebook ID obtained from listing notebooks in the site
    sections_list_url_sharepoint = f"https://graph.microsoft.com/v1.0/sites/{sharepoint_site_id}/onenote/notebooks/{target_onenote_notebook_id}/sections"
    pages_in_section_url_template_sharepoint = f"https://graph.microsoft.com/v1.0/sites/{sharepoint_site_id}/onenote/sections/{{section_id}}/pages?$orderby=createdDateTime asc"
    page_content_url_template_sharepoint = f"https://graph.microsoft.com/v1.0/sites/{sharepoint_site_id}/onenote/pages/{{page_id}}/content"


    # 1. Fetch all sections for the TARGET_ONENOTE_NOTEBOOK_ID
    sections = []
    url = sections_list_url_sharepoint
    logger.info(
        f"Starting to fetch OneNote sections from SharePoint notebook..."
    )
    try:
        while url:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            sections.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
        logger.info(
            f"There are {len(sections)} sections in the SharePoint notebook."
        )
    except RequestException as e:
        logger.error(
            f"Failed to fetch sections from SharePoint notebook, stopping sync: {e}"
        )
        return []

    # 2. For each section, fetch its page metadata
    all_pages_metadata = []
    logger.info("Fetching page metadata for each section in SharePoint notebook...")
    for section in sections:
        section_id = section.get("id")
        section_name = section.get("displayName")
        
        if not section_id or not section_name:
            continue

        # Use the SharePoint-specific template for pages in a section
        page_url = pages_in_section_url_template_sharepoint.format(
            section_id=section_id
        )
        try:
            while page_url:
                response = requests.get(page_url, headers=headers)
                response.raise_for_status()
                data = response.json()
                pages_in_section = data.get("value", [])
                for page in pages_in_section:
                    page["sectionDisplayName"] = (
                        section_name  # Add section name to page metadata
                    )
                all_pages_metadata.extend(pages_in_section)
                page_url = data.get("@odata.nextLink")
        except RequestException as e:
            logger.error(
                f"Failed to fetch pages for SharePoint section {section_id} ('{section_name}'): {e}"
            )
            continue

    logger.info(
        f"Finished fetching metadata for {len(all_pages_metadata)} pages from SharePoint notebook. Now fetching raw HTML content."
    )

    # 3. For each page, fetch its raw HTML content
    all_pages_data = []
    for page_meta in all_pages_metadata:
        page_id = page_meta.get("id")
        if not page_id:
            continue

        # Use the SharePoint-specific template for page content
        content_url = page_content_url_template_sharepoint.format(page_id=page_id)
        try:
            response = requests.get(content_url, headers=headers)
            response.raise_for_status()
            html_content = response.text

            page_meta["html_content"] = html_content
            all_pages_data.append(page_meta)
            logger.info(
                f"Successfully fetched content for section: [{page_meta.get('sectionDisplayName', '')}] page: {page_meta.get('title', '')}"
            )

        except RequestException as e:
            logger.error(f"Failed to fetch content for SharePoint page {page_id}: {e}")
            continue

    logger.info(
        f"Successfully fetched raw content for {len(all_pages_data)} pages from SharePoint notebook."
    )
    return all_pages_data
