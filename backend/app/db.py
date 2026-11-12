from contextlib import contextmanager
import logging
import os
from collections.abc import Iterator

import psycopg
from psycopg.rows import dict_row


logger = logging.getLogger(__name__)


class DatabaseConfigurationError(RuntimeError):
    """Raised when the backend has not been given a PostgreSQL connection URL."""


class DatabaseConnectionError(RuntimeError):
    """Raised when PostgreSQL cannot be reached or a database operation fails."""


class DatabaseIntegrityError(DatabaseConnectionError):
    """Raised when PostgreSQL rejects data because of a constraint violation."""


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise DatabaseConfigurationError("DATABASE_URL is not configured")

    try:
        with psycopg.connect(
            database_url,
            row_factory=dict_row,
            connect_timeout=10,
        ) as connection:
            yield connection
    except psycopg.IntegrityError as exc:
        logger.warning("PostgreSQL integrity constraint rejected an operation", exc_info=True)
        raise DatabaseIntegrityError("Database constraint violation") from exc
    except psycopg.Error as exc:
        logger.exception("PostgreSQL operation failed")
        raise DatabaseConnectionError("Database operation failed") from exc
