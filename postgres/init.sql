-- =========================================================
-- Extensions
-- =========================================================
CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- =========================================================
-- Create application database + n8n database
-- =========================================================
SELECT 'CREATE DATABASE loan_db'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'loan_db'
)\gexec

SELECT 'CREATE DATABASE n8n_db'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'n8n_db'
)\gexec


-- =========================================================
-- Switch into application database
-- =========================================================
\connect loan_db


-- ---------------------------------------------------------
-- Upload batches (ingestion audit trail)
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS upload_batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    s3_key VARCHAR(500),
    filename VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'processing',
    records_processed INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);


-- ---------------------------------------------------------
-- Users
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    monthly_income NUMERIC(12,2) NOT NULL,
    credit_score INTEGER NOT NULL,
    employment_status VARCHAR(100),
    age INTEGER,
    upload_batch_id UUID REFERENCES upload_batches(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id)
);


-- ---------------------------------------------------------
-- Loan products
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS loan_products (
    id BIGSERIAL PRIMARY KEY,
    product_name VARCHAR(255) NOT NULL,
    provider VARCHAR(255),
    interest_rate NUMERIC(5,2),
    min_monthly_income NUMERIC(12,2),
    min_credit_score INTEGER,
    min_age INTEGER,
    max_age INTEGER,
    employment_statuses TEXT[],
    eligibility_text TEXT,
    source_url TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (product_name, provider)
);


-- ---------------------------------------------------------
-- Matches
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS matches (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    product_id BIGINT REFERENCES loan_products(id) ON DELETE CASCADE,
    match_score NUMERIC(5,2),
    match_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notified_at TIMESTAMP,
    UNIQUE (user_id, product_id)
);


-- ---------------------------------------------------------
-- Indexes for matching performance
-- ---------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_users_batch
    ON users(upload_batch_id);

CREATE INDEX IF NOT EXISTS idx_users_eligibility
    ON users(monthly_income, credit_score, age, employment_status);

CREATE INDEX IF NOT EXISTS idx_loan_products_eligibility
    ON loan_products(min_monthly_income, min_credit_score, min_age, max_age);

CREATE INDEX IF NOT EXISTS idx_matches_user
    ON matches(user_id);

CREATE INDEX IF NOT EXISTS idx_matches_product
    ON matches(product_id);

CREATE INDEX IF NOT EXISTS idx_matches_notified
    ON matches(notified_at);
