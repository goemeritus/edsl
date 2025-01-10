import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(
    log_dir: str = "logs",
    log_file: str = "edsl.log",
    file_level: int = logging.DEBUG,
    console_level: int = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> None:
    """Configure logging for the EDSL framework.

    Args:
        log_dir: Directory where log files will be stored
        log_file: Name of the log file
        file_level: Logging level for file output
        console_level: Logging level for console output. If None, no console output
        max_bytes: Maximum size of each log file
        backup_count: Number of backup files to keep
    """
    # Create logs directory if it doesn't exist
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    # Configure the root logger
    root_logger = logging.getLogger()

    # Clear any existing handlers to avoid duplicate logs
    root_logger.handlers.clear()

    # Create file handler for all logs
    file_handler = RotatingFileHandler(
        log_path / log_file, maxBytes=max_bytes, backupCount=backup_count
    )
    file_handler.setLevel(file_level)

    # Create formatter and add it to the handlers
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(formatter)

    # Add file handler to the root logger
    root_logger.addHandler(file_handler)

    # Only add console handler if console_level is specified
    if console_level is not None:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(console_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # Set overall logging level to file_level since we always want file logging
    root_logger.setLevel(file_level)


if __name__ == "__main__":
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
