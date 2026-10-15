import logging
import os
import uuid
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from . import csv_processor, n8n_client, postgres_service
from .config import settings
from .db import get_cursor
from .loan_catalog import LOAN_PRODUCTS


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="ClickPe Loan Eligibility Engine",
    description="Local-first loan eligibility matching pipeline.",
    version="0.3.0",
)

# Open for the local dashboard. Restrict this before a public deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _json_safe(value):
    if isinstance(value, (UUID, datetime, date)):
        return str(value)
    return value


@app.get("/")
def root():
    return {
        "service": "ClickPe Loan Eligibility Engine",
        "status": "running",
        "version": "0.3.0",
    }


@app.get("/health")
def health():
    try:
        with get_cursor(commit=False) as cur:
            cur.execute("SELECT 1")
            cur.fetchone()

        return {"status": "healthy", "database": "connected"}

    except Exception as exc:
        logger.exception("Health check failed")
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(exc),
        }


@app.post("/upload")
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Only .csv files are accepted")

    raw = await file.read()

    if len(raw) == 0:
        raise HTTPException(400, "Empty file")

    if len(raw) > settings.MAX_CSV_BYTES:
        raise HTTPException(
            413,
            f"CSV exceeds {settings.MAX_CSV_BYTES} bytes",
        )

    # Local storage stands in for S3 during development.
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    s3_key = f"uploads/{uuid.uuid4()}-{file.filename}"
    local_path = os.path.join(
        settings.UPLOAD_DIR,
        os.path.basename(s3_key),
    )

    with open(local_path, "wb") as fh:
        fh.write(raw)

    batch_id = postgres_service.create_batch(
        s3_key=s3_key,
        filename=file.filename,
    )

    logger.info("Created batch %s for %s", batch_id, file.filename)

    try:
        valid_rows, row_errors = csv_processor.parse_and_validate(raw)

    except csv_processor.CSVValidationError as exc:
        postgres_service.update_batch(
            batch_id,
            status="failed",
            error=str(exc),
        )
        raise HTTPException(400, str(exc))

    inserted = postgres_service.bulk_insert_users(
        batch_id,
        valid_rows,
    )

    postgres_service.update_batch(
        batch_id,
        status="completed",
        processed=inserted,
        failed=len(row_errors),
    )

    # Don't fail the upload if n8n is temporarily unavailable.
    await n8n_client.trigger_ingest_complete(batch_id)

    return {
        "batch_id": batch_id,
        "filename": file.filename,
        "records_processed": inserted,
        "records_failed": len(row_errors),
        "errors": row_errors[:25],
    }


@app.get("/batches/{batch_id}")
def get_batch(batch_id: str):
    row = postgres_service.get_batch(batch_id)

    if not row:
        raise HTTPException(404, "batch not found")

    return {k: _json_safe(v) for k, v in row.items()}


@app.get("/users")
def list_users(limit: int = 100):
    with get_cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT user_id, email, monthly_income, credit_score,
                   employment_status, age
              FROM users
             ORDER BY user_id
             LIMIT %s
            """,
            (limit,),
        )

        return {"users": [dict(r) for r in cur.fetchall()]}


@app.get("/loan-products")
def list_loan_products():
    with get_cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT product_name, provider, interest_rate,
                   min_monthly_income, min_credit_score,
                   min_age, max_age
              FROM loan_products
             ORDER BY interest_rate
            """
        )

        return {"products": [dict(r) for r in cur.fetchall()]}


@app.get("/matches")
def list_matches(limit: int = 500):
    with get_cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT m.user_id,
                   u.email,
                   p.product_name,
                   p.provider,
                   p.interest_rate,
                   m.match_score,
                   m.match_reason,
                   m.notified_at
              FROM matches m
              JOIN users u ON u.user_id = m.user_id
              JOIN loan_products p ON p.id = m.product_id
             ORDER BY m.user_id, m.match_score DESC
             LIMIT %s
            """,
            (limit,),
        )

        rows = cur.fetchall()

        return {
            "matches": [
                {
                    **{
                        k: v
                        for k, v in r.items()
                        if k != "notified_at"
                    },
                    "notified": r["notified_at"] is not None,
                }
                for r in rows
            ]
        }


@app.get("/mock/loan-products")
def mock_loan_products():
    # Used by the local n8n workflow instead of a live crawler.
    return {
        "count": len(LOAN_PRODUCTS),
        "products": LOAN_PRODUCTS,
    }


@app.post("/dev/rematch/{batch_id}")
async def dev_rematch(batch_id: str):
    ok = await n8n_client.trigger_ingest_complete(batch_id)

    return {
        "triggered": ok,
        "batch_id": batch_id,
    }