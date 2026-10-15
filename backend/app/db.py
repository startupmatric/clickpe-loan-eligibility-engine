from contextlib import contextmanager
from typing import Iterator

import psycopg2
import psycopg2.extras

from .config import settings


def _connect():
    return psycopg2.connect(settings.DATABASE_URL)


@contextmanager
def get_cursor(commit: bool = True) -> Iterator[psycopg2.extras.RealDictCursor]:
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
