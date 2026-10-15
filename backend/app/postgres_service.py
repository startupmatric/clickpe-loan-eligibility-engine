from typing import Any, Iterable

from psycopg2.extras import execute_batch

from .db import get_cursor


def create_batch(s3_key: str, filename: str) -> str:
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO upload_batches (s3_key, filename, status)
            VALUES (%s, %s, 'processing')
            RETURNING id
            """,
            (s3_key, filename),
        )
        return str(cur.fetchone()["id"])


def update_batch(batch_id, *, status, processed=0, failed=0, error=None):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE upload_batches
               SET status = %s,
                   records_processed = %s,
                   records_failed = %s,
                   error_message = %s,
                   completed_at = NOW()
             WHERE id = %s
            """,
            (status, processed, failed, error, batch_id),
        )


def bulk_insert_users(batch_id: str, rows: Iterable[dict[str, Any]]) -> int:
    rows = list(rows)
    if not rows:
        return 0

    values = [
        (r["user_id"], r["email"], r["monthly_income"], r["credit_score"],
         r["employment_status"], r["age"], batch_id)
        for r in rows
    ]

    with get_cursor() as cur:
        execute_batch(
            cur,
            """
            INSERT INTO users
                (user_id, email, monthly_income, credit_score,
                 employment_status, age, upload_batch_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE
              SET email             = EXCLUDED.email,
                  monthly_income    = EXCLUDED.monthly_income,
                  credit_score      = EXCLUDED.credit_score,
                  employment_status = EXCLUDED.employment_status,
                  age               = EXCLUDED.age,
                  upload_batch_id   = EXCLUDED.upload_batch_id
            """,
            values,
            page_size=500,
        )
    return len(values)


def get_batch(batch_id: str) -> dict | None:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM upload_batches WHERE id = %s", (batch_id,))
        return cur.fetchone()


def list_matches_for_user(user_id: str) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT m.user_id, m.match_score, m.match_reason,
                   p.product_name, p.provider, p.interest_rate
              FROM matches m
              JOIN loan_products p ON p.id = m.product_id
             WHERE m.user_id = %s
             ORDER BY m.match_score DESC
            """,
            (user_id,),
        )
        return cur.fetchall()
