import os
import sys
import logging
from logging.handlers import RotatingFileHandler

def setup_logger(log_dir: str = "logs", level: int = logging.INFO) -> logging.Logger:
    """Configures rotating file handler and console handler for logging."""
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "downloader.log")
    
    logger = logging.getLogger("TelegramDownloader")
    logger.setLevel(level)
    
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)-5s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Rotating File Handler (10MB per file, up to 5 backups)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    logger.addHandler(file_handler)

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    return logger

logger = setup_logger()
