"""
Mock loan product catalog.

In production this data would come from crawling real bank/fintech
product pages (see n8n Workflow A). For the local demo we serve a
static, realistic catalog so the whole pipeline is self-contained.
"""
from typing import Any


LOAN_PRODUCTS: list[dict[str, Any]] = [
    {
        "product_name": "SBI Personal Loan",
        "provider": "State Bank of India",
        "interest_rate": 11.15,
        "min_monthly_income": 25000,
        "min_credit_score": 700,
        "min_age": 21,
        "max_age": 60,
        "employment_statuses": ["salaried"],
        "eligibility_text": "Salaried individuals with minimum monthly income of Rs 25,000 and CIBIL score of 700 or above.",
        "source_url": "https://sbi.co.in/web/personal-banking/loans/personal-loans",
    },
    {
        "product_name": "HDFC Bank Personal Loan",
        "provider": "HDFC Bank",
        "interest_rate": 10.75,
        "min_monthly_income": 30000,
        "min_credit_score": 720,
        "min_age": 21,
        "max_age": 60,
        "employment_statuses": ["salaried", "self_employed"],
        "eligibility_text": "Salaried or self-employed professionals aged 21-60 with monthly income of Rs 30,000+ and credit score 720+.",
        "source_url": "https://www.hdfcbank.com/personal/borrow/popular-loans/personal-loan",
    },
    {
        "product_name": "Bajaj Finserv Personal Loan",
        "provider": "Bajaj Finance",
        "interest_rate": 12.50,
        "min_monthly_income": 22000,
        "min_credit_score": 685,
        "min_age": 23,
        "max_age": 58,
        "employment_statuses": ["salaried", "self_employed"],
        "eligibility_text": "Indian residents aged 23-58 with stable income and credit score 685+.",
        "source_url": "https://www.bajajfinserv.in/personal-loan",
    },
    {
        "product_name": "ICICI Bank Personal Loan",
        "provider": "ICICI Bank",
        "interest_rate": 10.85,
        "min_monthly_income": 27500,
        "min_credit_score": 700,
        "min_age": 21,
        "max_age": 58,
        "employment_statuses": ["salaried"],
        "eligibility_text": "Salaried applicants with monthly income of Rs 27,500+ and CIBIL 700+.",
        "source_url": "https://www.icicibank.com/personal-banking/loans/personal-loan",
    },
    {
        "product_name": "Kotak Mahindra Personal Loan",
        "provider": "Kotak Mahindra Bank",
        "interest_rate": 11.25,
        "min_monthly_income": 25000,
        "min_credit_score": 690,
        "min_age": 21,
        "max_age": 60,
        "employment_statuses": ["salaried", "self_employed"],
        "eligibility_text": "Salaried or self-employed, age 21-60, monthly income Rs 25,000+.",
        "source_url": "https://www.kotak.com/en/personal-banking/loans/personal-loan.html",
    },
    {
        "product_name": "Axis Bank Personal Loan",
        "provider": "Axis Bank",
        "interest_rate": 11.50,
        "min_monthly_income": 20000,
        "min_credit_score": 680,
        "min_age": 21,
        "max_age": 60,
        "employment_statuses": ["salaried", "self_employed"],
        "eligibility_text": "Age 21-60, salaried or self-employed, credit score 680+.",
        "source_url": "https://www.axisbank.com/retail/loans/personal-loan",
    },
]
