from loguru import logger
import sys
from pathlib import Path

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent # Adjusted for new location app/core/


def setup_logging(env: str = "dev"):
    """Configure logging settings for the application."""
    logger.remove()

    console_log_levels = {
        "dev": "DEBUG",
        "test": "INFO",
        "prod": "WARNING",
    }
    console_level = console_log_levels.get(env, "DEBUG")

    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)

    log_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | " \
                 "<level>{level: <5}</level> | " \
                 "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | " \
                 "<level>{message}</level>"


    # DEBUG 
    logger.add(
        log_dir / "app-debug.log",
        rotation="10 MB",
        retention="10 days",  
        compression="zip",
        level="DEBUG",
        format=log_format,
        enqueue=True,
        filter=lambda record: record["level"].name == "DEBUG"
    )

    logger.add(
        log_dir / "app.log",
        rotation="10 MB",
        retention="1 days",
        compression="zip",
        level="INFO",
        format=log_format,
        enqueue=True,
        # filter=lambda record: record["level"].name not in ["DEBUG"]
    )

    logger.add(
        sys.stderr,
        level=console_level,
        format= "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | " \
                 "<level>{level: <5}</level> | " \
                 "<cyan>{file}</cyan>:<cyan>{line}</cyan> | " \
                 "<level>{message}</level>",
        colorize=True,
    ) 