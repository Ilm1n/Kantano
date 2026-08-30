"""
Centralized logging configuration for the Light Task application.
Provides structured logging with JSON output for production and human-readable for development.
"""

import json
import logging
import logging.config
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id  # type: ignore
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id  # type: ignore

        return json.dumps(log_data)


def setup_logging() -> None:
    """Configure logging for the application."""

    # Create logs directory BEFORE configuring logging
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
            "detailed": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
            },
            "json": {
                "()": JSONFormatter,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "INFO",  # Reduced from DEBUG for production
                "formatter": "default",
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "INFO",
                "formatter": "json",
                "filename": "logs/app.log",
                "maxBytes": 5242880,  # Reduced from 10MB to 5MB for VPS
                "backupCount": 3,  # Reduced from 5 to 3 (max 15MB total)
            },
            "timed_file": {
                "class": "logging.handlers.TimedRotatingFileHandler",
                "level": "INFO",
                "formatter": "json",
                "filename": "logs/app.log",
                "when": "midnight",  # Daily rotation at midnight
                "interval": 1,
                "backupCount": 3,  # Keep 3 days of logs
            },
        },
        "loggers": {
            "src": {
                "level": "INFO",  # Reduced from DEBUG
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "fastapi": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
            "sqlalchemy": {
                "level": "WARNING",
                "handlers": ["console"],
                "propagate": False,
            },
        },
        "root": {
            "level": "INFO",
            "handlers": ["console"],
        },
    }

    logging.config.dictConfig(config)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name."""
    return logging.getLogger(name)


# Convenience loggers for common modules
auth_logger = get_logger("src.auth")
db_logger = get_logger("src.db")
s3_logger = get_logger("src.s3")
user_logger = get_logger("src.users")
board_logger = get_logger("src.boards")
project_logger = get_logger("src.projects")
invitation_logger = get_logger("src.invitations")
registration_logger = get_logger("src.registration")
