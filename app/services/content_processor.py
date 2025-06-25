import base64
import hashlib
import os
import json
import requests
import boto3
import filetype
import time
import random
from botocore.exceptions import ClientError
from bs4 import BeautifulSoup, NavigableString
from typing import List, Dict, Any, Optional, Literal
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from loguru import logger


class ContentProcessor:
    """
    Processes HTML content from OneNote pages by parsing text, handling images,
    chunking text, and generating vector embeddings.
    Allows specifying different model providers for table and image processing.
    """
    def __init__(self, chunk_size: int = 1024, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.image_storage_path = Path(settings.IMAGE_STORAGE_PATH).expanduser()
        self.image_storage_path.mkdir(parents=True, exist_ok=True)
        self.img_prompt = (
            """
            Provide a concise and informative description of this image or screenshot.
            Focus on key visual elements, any visible text, labels, or data.
            If this is a screenshot, summarize the main interface or process shown, 
            and explain its relevance to the surrounding document or instructions.
            """
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            is_separator_regex=False,
        )

        try:
            logger.info("Initializing Bedrock Runtime client...")
            self.bedrock_client = boto3.client(
                service_name='bedrock-runtime',
                region_name=settings.AWS_REGION_NAME,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
            )
            logger.info("Bedrock Runtime client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Bedrock client: {e}")
            raise

    def _invoke_bedrock(self, model_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """Generic method to invoke a Bedrock model without retry logic."""
        try:
            response = self.bedrock_client.invoke_model(
                body=json.dumps(body),
                modelId=model_id,
                contentType='application/json',
                accept='application/json'
            )
            return json.loads(response.get('body').read())
        except ClientError as e:
            logger.error(f"A Bedrock client error occurred when invoking {model_id}: {e}")
            raise

    def _get_img_description_from_claude(self, base64_image: str, media_type: str) -> str:
        """Reusable method to get a image description from an Anthropic Claude model."""
        content = [
            {"type": "text", "text": self.img_prompt},
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": base64_image}}
        ]
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 300,
            "messages": [{"role": "user", "content": content}]
        }

        response_body = self._invoke_bedrock("apac.anthropic.claude-3-haiku-20240307-v1:0", request_body)
        return response_body.get('content', [{}])[0].get('text', '')

    def _get_img_description_from_amazon(self, base64_image: str, media_type: str) -> str:
        """Reusable method to get an image description from an Amazon Nova Lite model."""
        content = [
            {
                "image": {
                    "format": "png",
                    "source": { "bytes": base64_image }
                }
            },
            {"text": self.img_prompt}
        ]
        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ],
            "inferenceConfig": {
                "max_new_tokens": 300,
                "temperature": 0.5,
                "top_p": 0.9
            }
        }
        response_body = self._invoke_bedrock("apac.amazon.nova-lite-v1:0", request_body)
        return response_body.get('output', {}).get('message', {}).get('content', [{}])[0].get('text', '')

    def _get_table_summary_from_amazon(self, prompt: str) -> str:
        """Reusable method to get a summary from an Amazon Titan Text model."""

        messages = [
                {"role": "user", "content": [{"text": prompt}]}
            ]

        inference_config = {
            "max_new_tokens": 1000,
            "top_p": 0.9,
            "temperature": 0.1, 
        }

        request_body = {
            "messages": messages,
            "inferenceConfig": inference_config,
        }
        response_body = self._invoke_bedrock("apac.amazon.nova-lite-v1:0", request_body)
        return response_body.get('output', {}).get('message', {}).get('content', [{}])[0].get('text', '')

    def _table_to_markdown(self, table_tag: NavigableString) -> str:
        """Converts an HTML table into a Markdown string."""
        markdown_table = []
        rows = table_tag.find_all('tr')
        if not rows:
            return ""

        # Header
        header_cells = rows[0].find_all(['th', 'td'])
        header_texts = [cell.get_text(strip=True) for cell in header_cells]
        markdown_table.append('| ' + ' | '.join(header_texts) + ' |')

        # Separator
        markdown_table.append('| ' + ' | '.join(['---'] * len(header_cells)) + ' |')

        # Body
        for row in rows[1:]:
            cols = [cell.get_text(strip=True) for cell in row.find_all(['th', 'td'])]
            markdown_table.append('| ' + ' | '.join(cols) + ' |')

        return '\n'.join(markdown_table)

    def _process_table(self, table_tag: NavigableString) -> str:
        """Converts table to Markdown and generates a summary using Titan Text."""
        markdown_table = self._table_to_markdown(table_tag)
        if not markdown_table.strip():
            return ""
        try:
            prompt = f"Please provide a concise, but detailed summary of the following Markdown table:\n\n{markdown_table}"
            summary = self._get_table_summary_from_amazon(prompt)
            logger.info(f"Generated table summary using Titan: {summary.strip()}")
            return f"\n[Table Summary: {summary.strip()}]\n{markdown_table}\n"
        except Exception as e:
            logger.error(f"Failed to generate summary for table using Titan: {e}", exc_info=True)
            return f"\n[Table processing failed]\n{markdown_table}\n"

    def _process_image(self, img_tag: NavigableString, page_id: str, access_token: str) -> str:
        """Downloads an image and gets a description using Claude."""
        src = img_tag.get('src', '')
        if not src or '/onenote/resources/' not in src:
            return ""
        try:
            logger.info(f"Downloading image from: {src}")
            headers = {'Authorization': f'Bearer {access_token}'}
            response = requests.get(src, headers=headers)
            response.raise_for_status()
            image_data = response.content

            kind = filetype.guess(image_data)
            content_type, file_extension = (kind.mime, kind.extension) if kind else ('image/png', 'png')

            image_hash = hashlib.sha256(image_data).hexdigest()
            image_dir = self.image_storage_path / page_id
            image_dir.mkdir(exist_ok=True)
            image_path = image_dir / f"{image_hash}.{file_extension}"

            with open(image_path, "wb") as f:
                f.write(image_data)
            logger.info(f"Saved image to {image_path}")

            base64_encoded_image = base64.b64encode(image_data).decode('utf-8')

            description = self._get_img_description_from_claude(base64_encoded_image, content_type)
            logger.info(f"Generated image description using Amazon: {description.strip()}")
            return f"\n[Image Source: {str(image_path)}, Description: {description.strip()}]\n"
        except Exception as e:
            logger.error(f"Failed to process image using {self.image_model}: {e}", exc_info=True)
            return "\n[Image processing failed]\n"

    def _chunk_text(self, text: str) -> List[str]:
        """Splits text into overlapping chunks using RecursiveCharacterTextSplitter."""
        if not text:
            return []
        return self.text_splitter.split_text(text)

    def _embed_chunks(self, chunks: List[str]) -> List[List[float]]:
        """Generates vector embeddings for a list of text chunks."""
        embeddings = []
        for chunk in chunks:
            try:
                body = {"inputText": chunk}
                response_body = self._invoke_bedrock(settings.EMBEDDING_MODEL_ID, body)
                embeddings.append(response_body['embedding'])
            except Exception as e:
                logger.error(f"Failed to embed chunk: '{chunk[:50]}...'. Error: {e}")
                embeddings.append([])
        return embeddings

    def process_page(self, page_data: Dict[str, Any], access_token: str) -> List[Dict[str, Any]]:
        """Main function to process a single OneNote page."""
        page_html = page_data.get('html_content', '')
        page_id = page_data.get('id')
        if not page_id or not page_html:
            return []

        logger.info(f"Processing page {page_id}")

        soup = BeautifulSoup(page_html, 'html.parser')

        # Replace tables and images with their text representations
        for table in soup.find_all('table'):
            table.replace_with(NavigableString(self._process_table(table)))
        for img in soup.find_all('img'):
            img.replace_with(NavigableString(self._process_image(img, page_id, access_token)))

        # Extract clean text
        clean_text = soup.get_text(separator='\n', strip=True)
        title = page_data.get('title', '')
        # Chunk text
        text_chunks = self._chunk_text(clean_text)
        logger.info(f"Split page ('{title}') {page_id} into {len(text_chunks)} chunks.")

        # Get embeddings
        chunk_embeddings = self._embed_chunks(text_chunks)

        # Prepare data for Milvus
        milvus_chunks = []
        for i, text_chunk in enumerate(text_chunks):
            if i < len(chunk_embeddings) and chunk_embeddings[i]:
                milvus_chunks.append({
                    "vector": chunk_embeddings[i],
                    "page_id": page_id,
                    "text_content": text_chunk,
                    "page_title": title,
                    "section_name": page_data.get('sectionDisplayName', '')
                })

        logger.info(
            f"Successfully processed page ('{title}') {page_id}, created {len(milvus_chunks)} embeddable chunks."
        )
        return milvus_chunks 
