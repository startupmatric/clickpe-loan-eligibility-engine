"""Unit tests for the CSV validation pipeline."""
import sys
from pathlib import Path

import pytest

# Make backend/app importable when running pytest from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.csv_processor import CSVValidationError, parse_and_validate  # noqa: E402


VALID_CSV = b"""user_id,email,monthly_income,credit_score,employment_status,age
u001,alice@example.com,85000,780,salaried,32
u002,bob@example.com,42000,690,self_employed,45
"""


def test_valid_csv_returns_all_rows():
    rows, errors = parse_and_validate(VALID_CSV)
    assert len(rows) == 2
    assert errors == []
    assert rows[0]["user_id"] == "u001"
    assert rows[0]["email"] == "alice@example.com"
    assert rows[0]["monthly_income"] == 85000.0
    assert rows[0]["credit_score"] == 780
    assert rows[0]["employment_status"] == "salaried"
    assert rows[0]["age"] == 32


def test_missing_required_column_raises():
    bad = b"user_id,email,monthly_income\n"
    with pytest.raises(CSVValidationError, match="Missing required columns"):
        parse_and_validate(bad)


def test_invalid_email_becomes_row_error():
    bad = VALID_CSV + b"u003,not-an-email,30000,700,salaried,28\n"
    rows, errors = parse_and_validate(bad)
    assert len(rows) == 2
    assert any("invalid email" in e for e in errors)


def test_credit_score_out_of_range():
    bad = VALID_CSV + b"u003,x@y.com,30000,999,salaried,28\n"
    rows, errors = parse_and_validate(bad)
    assert len(rows) == 2
    assert any("credit_score out of range" in e for e in errors)


def test_age_out_of_range():
    bad = VALID_CSV + b"u003,x@y.com,30000,700,salaried,15\n"
    rows, errors = parse_and_validate(bad)
    assert len(rows) == 2
    assert any("age out of range" in e for e in errors)


def test_empty_csv_raises():
    with pytest.raises(CSVValidationError, match="no data rows"):
        parse_and_validate(b"user_id,email,monthly_income,credit_score,employment_status,age\n")


def test_employment_status_normalized_to_lowercase():
    raw = b"""user_id,email,monthly_income,credit_score,employment_status,age
u001,a@b.com,50000,700,SALARIED,30
"""
    rows, _ = parse_and_validate(raw)
    assert rows[0]["employment_status"] == "salaried"


def test_mixed_valid_and_invalid_rows():
    raw = b"""user_id,email,monthly_income,credit_score,employment_status,age
u001,alice@example.com,85000,780,salaried,32
u002,not-an-email,42000,690,self_employed,45
u003,carol@example.com,15000,540,student,22
u004,dan@example.com,60000,720,salaried,29
u005,eve@example.com,120000,810,salaried,38
u006,invalid-email,25000,650,salaried,28
"""
    rows, errors = parse_and_validate(raw)
    assert len(rows) == 4
    assert len(errors) == 2
    assert all("invalid email" in e for e in errors)