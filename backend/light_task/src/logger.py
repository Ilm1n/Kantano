import logging

from src.config import settings
from src.observability.logging import setup_logging as _setup_logging


def setup_logging() -> None:
    _setup_logging(settings.observability)


def get_logger(name: str) -> logging.Logger:
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
