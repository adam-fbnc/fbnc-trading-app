"""
Centralized logging configuration.

Call setup_logging() once at app startup (before anything logs). Honors
LOG_LEVEL and SQL_ECHO from settings/.env so verbosity is controllable
without code changes.
"""
import logging
import sys

from app.core.config import settings

_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Reset handlers so re-running (e.g. uvicorn --reload) doesn't duplicate lines
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    root.addHandler(handler)

    # App loggers follow the configured level
    logging.getLogger("app").setLevel(level)

    # SQLAlchemy engine logging is controlled separately to avoid noise
    sql_level = logging.INFO if settings.sql_echo else logging.WARNING
    logging.getLogger("sqlalchemy.engine").setLevel(sql_level)

    # Tame noisy third-party loggers unless we're in DEBUG
    if level > logging.DEBUG:
        logging.getLogger("watchfiles").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging configured — level=%s sql_echo=%s", settings.log_level.upper(), settings.sql_echo
    )
