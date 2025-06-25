from typing import List, Dict, Any
import requests
from requests.exceptions import RequestException

from loguru import logger

# Corrected URLs without select parameters
SECTIONS_LIST_URL = "https://graph.microsoft.com/v1.0/me/onenote/sections"
PAGES_IN_SECTION_URL_TEMPLATE = "https://graph.microsoft.com/v1.0/me/onenote/sections/{section_id}/pages?$orderby=createdDateTime asc"
PAGE_CONTENT_URL_TEMPLATE = "https://graph.microsoft.com/v1.0/me/onenote/pages/{page_id}/content"


def fetch_all_pages(access_token: str) -> List[Dict[str, Any]]:
    """
    Fetches all pages by first getting sections, then pages per section,
    returning the raw HTML content and metadata for each page.

    Args:
        access_token: Microsoft Graph API access token.

    Returns:
        A list of page data dictionaries. Returns an empty list on failure.
    """
    headers = {'Authorization': f'Bearer {access_token}'}

    # 1. Fetch all sections
    sections = []
    url = SECTIONS_LIST_URL
    logger.info("Starting to fetch all OneNote sections...")
    try:
        while url:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            sections.extend(data.get('value', []))
            url = data.get('@odata.nextLink')
        logger.info(f"Finished fetching {len(sections)} sections.")
    except RequestException as e:
        logger.error(f"Failed to fetch sections, stopping sync: {e}")
        return []

    # 2. For each section, fetch its page metadata
    all_pages_metadata = []
    logger.info("Fetching page metadata for each section...")
    for section in sections:
        section_id = section.get('id')
        section_name = section.get('displayName')
        if not section_id or not section_name:
            continue

        page_url = PAGES_IN_SECTION_URL_TEMPLATE.format(section_id=section_id)
        try:
            while page_url:
                response = requests.get(page_url, headers=headers)
                response.raise_for_status()
                data = response.json()
                pages_in_section = data.get('value', [])
                for page in pages_in_section:
                    page['sectionDisplayName'] = section_name
                all_pages_metadata.extend(pages_in_section)
                page_url = data.get('@odata.nextLink')
        except RequestException as e:
            logger.error(f"Failed to fetch pages for section {section_id} ('{section_name}'): {e}")
            continue

    logger.info(f"Finished fetching metadata for {len(all_pages_metadata)} pages. Now fetching raw HTML content.")

    # 3. For each page, fetch its raw HTML content
    all_pages_data = []
    for page_meta in all_pages_metadata:
        page_id = page_meta.get('id')
        if not page_id:
            continue

        content_url = PAGE_CONTENT_URL_TEMPLATE.format(page_id=page_id)
        try:
            response = requests.get(content_url, headers=headers)
            response.raise_for_status()
            html_content = response.text

            page_meta['html_content'] = html_content
            all_pages_data.append(page_meta)
            logger.info(
                f"Successfully fetched content for page: {page_meta.get('title', '')}"
            )

        except RequestException as e:
            logger.error(f"Failed to fetch content for page {page_id}: {e}")
            continue

    logger.info(f"Successfully fetched raw content for {len(all_pages_data)} pages.")
    return all_pages_data 
