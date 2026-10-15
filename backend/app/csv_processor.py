from io import BytesIO
from typing import Any

import pandas as pd


REQUIRED_COLUMNS = {
    "user_id",
    "email",
    "monthly_income",
    "credit_score",
    "employment_status",
    "age",
}


class CSVValidationError(Exception):
    pass


def parse_and_validate(raw: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        df = pd.read_csv(BytesIO(raw))
    except Exception as exc:
        raise CSVValidationError(f"Could not parse CSV: {exc}") from exc

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise CSVValidationError(f"Missing required columns: {sorted(missing)}")

    if df.empty:
        raise CSVValidationError("CSV contains no data rows")

    valid: list[dict[str, Any]] = []
    errors: list[str] = []

    for idx, row in df.iterrows():
        line = idx + 2
        try:
            user_id = str(row["user_id"]).strip()
            email = str(row["email"]).strip()
            if not user_id:
                raise ValueError("empty user_id")
            if not email or "@" not in email:
                raise ValueError("invalid email")

            monthly_income = float(row["monthly_income"])
            credit_score = int(row["credit_score"])
            age = int(row["age"])
            employment_status = str(row["employment_status"]).strip().lower()

            if monthly_income < 0:
                raise ValueError("negative monthly_income")
            if not (300 <= credit_score <= 900):
                raise ValueError("credit_score out of range (300-900)")
            if not (18 <= age <= 100):
                raise ValueError("age out of range (18-100)")
            if not employment_status:
                raise ValueError("empty employment_status")

            valid.append({
                "user_id": user_id,
                "email": email,
                "monthly_income": monthly_income,
                "credit_score": credit_score,
                "employment_status": employment_status,
                "age": age,
            })
        except Exception as exc:
            errors.append(f"line {line}: {exc}")

    return valid, errors
