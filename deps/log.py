"""Log to the console and to a rotating file."""

import logging
from logging.handlers import RotatingFileHandler

logger = logging.getLogger("family_bot")
logger.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

file_handler = RotatingFileHandler(
    "app.log", mode="a", maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8", delay=False
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(formatter)

if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


def print_log(message: str) -> None:
    """Log an info message."""
    logger.info(message)


def print_error_log(message: str) -> None:
    """Log an error message."""
    logger.error(message)


def print_warning_log(message: str) -> None:
    """Log a warning message."""
    logger.warning(message)
