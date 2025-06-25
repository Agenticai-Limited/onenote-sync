import time
import requests
from requests.exceptions import RequestException
from datetime import datetime, timedelta

from app.core.config import settings
from app.storage.db_handler import PostgresHandler

from loguru import logger

def get_access_token(
    user_email: str,
    max_retries: int = 3,
    backoff_factor: float = 0.5
) -> str:
    """
    Retrieves a new access token from Microsoft Graph API using a refresh token
    stored in the database. It updates the database with the new tokens upon success.

    Args:
        user_email: The email of the user to get the token for.
        max_retries: Maximum number of retry attempts for the API call.
        backoff_factor: Factor to determine the delay between retries.

    Returns:
        str: The new access token.

    Raises:
        Exception: If the token cannot be retrieved after all retries or if the user is not found.
    """
    pg_handler = None
    try:
        pg_handler = PostgresHandler()
        
        # 1. Get refresh token from the database
        logger.info(f"Fetching refresh token for user {user_email} from database...")
        auth_info = pg_handler.get_auth_by_email(user_email)
        if not auth_info or not auth_info.get('refresh_token'):
            raise Exception(f"Could not find valid authorization info or refresh token for user {user_email}.")
        
        refresh_token = auth_info['refresh_token']
        logger.info("Successfully fetched refresh token.")

        # 2. Prepare request to Microsoft Graph API
        payload = {
            'client_id': settings.MS_CLIENT_ID,
            'client_secret': settings.MS_CLIENT_SECRET,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
            'scope': settings.MS_GRAPH_SCOPE,
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        # 3. Make API call with retry logic
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempting to get new access token (attempt {attempt + 1}/{max_retries})...")
                response = requests.post(settings.MS_TOKEN_URL, data=payload, headers=headers)
                response.raise_for_status()

                token_data = response.json()
                new_access_token = token_data.get('access_token')
                new_refresh_token = token_data.get('refresh_token')
                expires_in = token_data.get('expires_in')

                if not all([new_access_token, new_refresh_token, expires_in]):
                    error_info = token_data.get('error_description', str(token_data))
                    logger.error(f"Incomplete token data received: {error_info}")
                    break  # Permanent failure, stop retrying

                # 4. Update database with new tokens
                expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in))
                pg_handler.update_auth_tokens(
                    email=user_email,
                    access_token=new_access_token,
                    refresh_token=new_refresh_token,
                    token_expires_at=expires_at
                )
                logger.info("Successfully obtained and updated Microsoft Graph API tokens.")
                return new_access_token

            except RequestException as e:
                status_code = e.response.status_code if e.response else None
                logger.warning(f"Request failed on attempt {attempt + 1}/{max_retries}: {e}")
                
                if status_code and 400 <= status_code < 500:
                    logger.error(f"Client error getting token: {status_code} {e.response.text}. This might indicate an invalid refresh token. Stopping retries.")
                    break
                
                if attempt < max_retries - 1:
                    sleep_time = backoff_factor * (2 ** attempt)
                    logger.info(f"Retrying in {sleep_time:.2f} seconds...")
                    time.sleep(sleep_time)

    except Exception as e:
        logger.error(f"An error occurred during the token refresh process: {e}", exc_info=True)
        # Re-raise the exception to be handled by the caller
        raise
    finally:
        if pg_handler:
            pg_handler.close()

    raise Exception("Failed to retrieve access token after multiple retries.") 