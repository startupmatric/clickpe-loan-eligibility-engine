import os


class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://loan_user:loan_password@postgres:5432/loan_db",
    )
    N8N_WEBHOOK_URL: str = os.getenv(
        "N8N_WEBHOOK_URL",
        "http://n8n:5678/webhook/ingest-complete",
    )
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "/app/uploads")
    MAX_CSV_BYTES: int = int(os.getenv("MAX_CSV_BYTES", str(20 * 1024 * 1024)))


settings = Settings()
