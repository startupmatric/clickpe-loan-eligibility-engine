"""Integration tests for the FastAPI surface.

These hit a running backend — they don't mock the database or the HTTP
layer. That means they catch things unit tests can't: connection strings,
schema drift, CORS, JSON serialization.

If the backend isn't running, every test in this file skips with a clear
reason instead of failing. That way you can run `pytest` on a laptop
without Docker and still get useful results from the unit tests.

To run:
    docker compose up -d backend
    cd backend
    python -m pytest tests -v
"""
import io
import os
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

API = os.getenv("API_URL", "http://localhost:8000")
TIMEOUT = 15


def _backend_up() -> bool:
    """Single source of truth for whether to skip this whole file."""
    try:
        return httpx.get(f"{API}/health", timeout=2).status_code == 200
    except Exception:
        return False


# This line skips every test below if the backend isn't reachable.
pytestmark = pytest.mark.skipif(
    not _backend_up(),
    reason=f"backend not reachable at {API} — start it with `docker compose up -d backend`",
)


# -----------------------------------------------------------------------------
# Health and root
# -----------------------------------------------------------------------------

def test_root_returns_service_info():
    r = httpx.get(f"{API}/", timeout=TIMEOUT)
    assert r.status_code == 200
    body = r.json()
    # We don't enforce the exact shape — just that it's a service descriptor.
    assert isinstance(body, dict)
    assert any(k in body for k in ("service", "status", "name"))


def test_health_endpoint_reports_healthy():
    r = httpx.get(f"{API}/health", timeout=TIMEOUT)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert body["database"] == "connected"


# -----------------------------------------------------------------------------
# /upload — happy path and validation failures
# -----------------------------------------------------------------------------

def test_upload_valid_csv_inserts_all_rows():
    csv = (
        b"user_id,email,monthly_income,credit_score,employment_status,age\n"
        b"itest_ok1,ok1@example.com,50000,720,salaried,30\n"
        b"itest_ok2,ok2@example.com,60000,750,self_employed,35\n"
        b"itest_ok3,ok3@example.com,80000,780,salaried,40\n"
    )
    files = {"file": ("it_valid.csv", io.BytesIO(csv), "text/csv")}
    r = httpx.post(f"{API}/upload", files=files, timeout=TIMEOUT)

    assert r.status_code == 200, r.text
    body = r.json()

    assert body["records_processed"] == 3
    assert body["records_failed"] == 0
    assert body["errors"] == []
    assert "batch_id" in body
    assert body["filename"] == "it_valid.csv"


def test_upload_rejects_missing_columns():
    csv = b"user_id,email\nitest_x,x@example.com\n"
    files = {"file": ("it_missing.csv", io.BytesIO(csv), "text/csv")}
    r = httpx.post(f"{API}/upload", files=files, timeout=TIMEOUT)

    assert r.status_code == 400
    assert "Missing required columns" in r.text


def test_upload_rejects_non_csv_file():
    files = {"file": ("notes.txt", io.BytesIO(b"not a csv"), "text/plain")}
    r = httpx.post(f"{API}/upload", files=files, timeout=TIMEOUT)

    assert r.status_code == 400
    assert "csv" in r.text.lower()


def test_upload_rejects_empty_csv():
    csv = b"user_id,email,monthly_income,credit_score,employment_status,age\n"
    files = {"file": ("it_empty.csv", io.BytesIO(csv), "text/csv")}
    r = httpx.post(f"{API}/upload", files=files, timeout=TIMEOUT)

    assert r.status_code == 400
    assert "no data rows" in r.text.lower() or "empty" in r.text.lower()


def test_upload_flags_invalid_email_as_row_error():
    csv = (
        b"user_id,email,monthly_income,credit_score,employment_status,age\n"
        b"itest_good,good@example.com,50000,720,salaried,30\n"
        b"itest_bad,not-an-email,50000,720,salaried,30\n"
    )
    files = {"file": ("it_mixed.csv", io.BytesIO(csv), "text/csv")}
    r = httpx.post(f"{API}/upload", files=files, timeout=TIMEOUT)

    assert r.status_code == 200
    body = r.json()

    assert body["records_processed"] == 1
    assert body["records_failed"] == 1
    assert len(body["errors"]) == 1
    assert "invalid email" in body["errors"][0]


def test_upload_flags_credit_score_out_of_range():
    csv = (
        b"user_id,email,monthly_income,credit_score,employment_status,age\n"
        b"itest_oob,oob@example.com,50000,999,salaried,30\n"
    )
    files = {"file": ("it_oob.csv", io.BytesIO(csv), "text/csv")}
    r = httpx.post(f"{API}/upload", files=files, timeout=TIMEOUT)

    assert r.status_code == 200
    body = r.json()

    assert body["records_processed"] == 0
    assert body["records_failed"] == 1
    assert any("credit_score out of range" in e for e in body["errors"])


def test_upload_flags_age_out_of_range():
    csv = (
        b"user_id,email,monthly_income,credit_score,employment_status,age\n"
        b"itest_yng,young@example.com,50000,720,salaried,15\n"
    )
    files = {"file": ("it_age.csv", io.BytesIO(csv), "text/csv")}
    r = httpx.post(f"{API}/upload", files=files, timeout=TIMEOUT)

    assert r.status_code == 200
    body = r.json()

    assert body["records_failed"] == 1
    assert any("age out of range" in e for e in body["errors"])


# -----------------------------------------------------------------------------
# Read-only endpoints
# -----------------------------------------------------------------------------

def test_list_users_returns_wrapped_list():
    r = httpx.get(f"{API}/users", timeout=TIMEOUT)
    assert r.status_code == 200
    body = r.json()
    assert "users" in body
    assert isinstance(body["users"], list)


def test_list_loan_products_returns_wrapped_list():
    r = httpx.get(f"{API}/loan-products", timeout=TIMEOUT)
    assert r.status_code == 200
    body = r.json()
    assert "products" in body
    assert isinstance(body["products"], list)
    # The catalog is seeded separately, but if it's populated the shape
    # should match what the dashboard expects.
    if body["products"]:
        p = body["products"][0]
        for key in ("product_name", "provider", "interest_rate"):
            assert key in p


def test_list_matches_returns_wrapped_list():
    r = httpx.get(f"{API}/matches", timeout=TIMEOUT)
    assert r.status_code == 200
    body = r.json()
    assert "matches" in body
    assert isinstance(body["matches"], list)


# -----------------------------------------------------------------------------
# Batch lookup
# -----------------------------------------------------------------------------

def test_batch_lookup_by_id_round_trips():
    # Upload one row so we have a known batch id
    csv = (
        b"user_id,email,monthly_income,credit_score,employment_status,age\n"
        b"itest_batch,batch@example.com,50000,720,salaried,30\n"
    )
    files = {"file": ("it_batch.csv", io.BytesIO(csv), "text/csv")}
    up = httpx.post(f"{API}/upload", files=files, timeout=TIMEOUT)
    assert up.status_code == 200
    batch_id = up.json()["batch_id"]

    r = httpx.get(f"{API}/batches/{batch_id}", timeout=TIMEOUT)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == batch_id
    assert body["status"] == "completed"
    assert body["records_processed"] >= 1


def test_batch_lookup_for_unknown_id_returns_404():
    r = httpx.get(f"{API}/batches/00000000-0000-0000-0000-000000000000", timeout=TIMEOUT)
    assert r.status_code == 404