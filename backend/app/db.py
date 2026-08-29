from contextlib import contextmanager
import os
from collections.abc import Iterator

import psycopg
from psycopg.rows import dict_row


class DatabaseConfigurationError(RuntimeError):
    """Raised when the backend has not been given a PostgreSQL connection URL."""


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise DatabaseConfigurationError("DATABASE_URL is not configured")

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        yield connection
