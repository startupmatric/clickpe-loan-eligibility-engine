# ClickPe Loan Eligibility Engine

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![n8n](https://img.shields.io/badge/n8n-workflows-EA4B71?logo=n8n&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)

Upload a CSV of applicants. The engine checks each one against a catalog of loan products, scores the matches, and emails everyone who qualifies.

It is a take-home for the ClickPe SDE Intern role. The whole stack runs locally with one `docker compose up -d`. No AWS account is needed, and `infrastructure/serverless.yml` shows how it maps to AWS.

## How it works

```
CSV file
  │
  ▼
FastAPI  POST /upload       validates every row, stores users, calls the n8n webhook
  │
  ▼
PostgreSQL                  users · loan_products · matches · upload_batches
  │
  ▼
n8n Workflow B              one SQL query filters, scores and writes matches
  │
  ▼
n8n Workflow C (every 1 min) emails unnotified matches, then marks them notified
  │
  ▼
MailHog inbox               one email per matched applicant
```

Rows that fail validation are reported by line number. Nothing is dropped silently.

## Quick start

**Requirements:** Docker Desktop with at least 6 GB of memory (8 GB on Windows, where n8n is heavier).

```bash
git clone <your-repo-url> clickpe-loan-engine
cd clickpe-loan-engine
docker compose up -d
```

The first start takes about a minute while n8n runs its database migrations.

**Check that it is running:**

```bash
docker compose ps          # 5 containers: postgres, backend, n8n, mailhog, frontend
curl http://localhost:8000/health
# {"status":"healthy","database":"connected"}
```

**Open the services:**

| Service | URL |
|---|---|
| Dashboard | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/docs |
| n8n | http://localhost:5678 |
| MailHog inbox | http://localhost:8025 |

### Import the n8n workflows

n8n does not read workflow files from disk, so this step is manual:

1. Open http://localhost:5678 and create the owner account (any email and password).
2. Go to **Workflows** in the left sidebar.
3. Choose **Import from File** and import all three files from `n8n/workflows/`.
4. On each Postgres node, reattach the `Loan DB Local` credential.
5. Switch **Active** on for all three workflows.

`n8n/workflows/README.md` covers the credential settings and common mistakes.

### Run the demo

```bash
curl -X POST -F "file=@data/sample_users.csv" http://localhost:8000/upload
```

```json
{
  "batch_id": "0887f79f-e16f-4029-b84e-6b0a65b8694d",
  "filename": "sample_users.csv",
  "records_processed": 5,
  "records_failed": 1,
  "errors": ["line 7: invalid email"]
}
```

Then open http://localhost:3000 to see applicants, matches and notifications. Four of the five sample applicants match at least one product, so MailHog receives four emails. The fifth (income 15,000, credit score 540) matches nothing and is correctly absent from the results.

## Matching without an LLM

The assignment calls this the "optimization treasure hunt". Here is how this repo handles it.

**The naive approach.** With 1,000 applicants and 30 products there are 30,000 eligibility decisions. Sending each one to an LLM means 30,000 API calls per upload, with high cost, high latency, non-deterministic answers, and no way to explain a match.

**What this repo does.** Eligibility is a set of rules over numbers and categories, so Postgres decides it in one query:

```sql
WHERE u.monthly_income >= l.min_monthly_income
  AND u.credit_score   >= l.min_credit_score
  AND u.age BETWEEN l.min_age AND l.max_age
  AND (l.employment_statuses IS NULL
       OR u.employment_status = ANY(l.employment_statuses))
```

Only pairs that pass are scored and stored. Indexes on the eligibility columns of `users` and `loan_products` keep the join fast as data grows. On the 5-applicant sample, 30 candidate pairs reduce to 21 matches.

**Scoring is a readable formula.**

```
match_score = 100 × (0.50 × credit_headroom
                   + 0.30 × income_headroom
                   + 0.20 × age_fit)
```

Every score comes from one SQL expression, so any match can be explained and reproduced.

**Where an LLM would fit.** It would not run per applicant. The design reserves it for turning scraped eligibility text into structured criteria, once per product (see [Known limitations](#known-limitations)).

| | LLM per pair | This system |
|---|---|---|
| LLM calls per 1,000-applicant upload | 30,000 | 0 |
| Cost of matching | High | None beyond the database |
| Reproducible | No | Yes |
| Auditable | No | Yes, the SQL is the source of truth |

## Dashboard

A single HTML file in `frontend/index.html`, with no framework and no build step. It includes:

- Overview with live counts and a matching funnel (candidate pairs, eligible matches, notified).
- Applicants, Loan Products and Matches tables with search and loading states.
- Drag-and-drop CSV upload with per-batch results.
- System health indicators for the API and database.
- Light and dark themes, saved between visits.

A framework would add overhead without benefit for an internal tool with a few tables and one form.

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Database connectivity check |
| `POST` | `/upload` | CSV → validate → store users → trigger matching |
| `GET` | `/batches/{id}` | Look up an upload batch |
| `GET` | `/users` | List applicants |
| `GET` | `/loan-products` | List the product catalog |
| `GET` | `/matches` | List matches |
| `GET` | `/mock/loan-products` | Static catalog standing in for a real crawler |
| `POST` | `/dev/rematch/{id}` | Re-run matching for a batch |

## Database

Four tables, defined in `postgres/init.sql`:

| Table | Purpose |
|---|---|
| `upload_batches` | One row per upload: filename, status, counts, timestamps. Use it to trace what happened. |
| `users` | One row per applicant: business key, eligibility fields, and the batch that brought them in. |
| `loan_products` | The catalog: eligibility thresholds, source URL, last updated. Unique on `(product_name, provider)`. |
| `matches` | One row per user and product that passed: score, reason, `notified_at`. Unique on `(user_id, product_id)`. |

Writes to `users` and `matches` use `ON CONFLICT DO UPDATE`, so re-running any step updates rows instead of duplicating them.

## n8n workflows

| File | Trigger | Job |
|---|---|---|
| `workflow-a-loan-discovery.json` | Every 6 hours | Fetch products and upsert into `loan_products` |
| `workflow-b-matching.json` | Webhook | Pre-filter with SQL, score, insert matches |
| `workflow-c-notification.json` | Every 1 minute | Email unnotified matches and mark them notified |

Workflow A reads from `/mock/loan-products`, which returns a 6-product catalog in the shape a real crawler would produce. The flow already keeps `source_url` for provenance, so moving to real bank pages means changing the URL and adding an HTML-parsing step.

## From local to AWS

| Local | AWS |
|---|---|
| FastAPI `/upload` | API Gateway + Lambda |
| `uploads/` volume | S3 bucket |
| PostgreSQL container | RDS PostgreSQL |
| n8n container | n8n on EC2 or ECS |
| MailHog | Amazon SES |
| `docker compose up -d` | `serverless deploy` |

The service boundaries stay the same, so the CSV parser, validation rules, matching SQL, workflows and dashboard do not change. `infrastructure/serverless.yml` is a deployable config. It keeps secrets in SSM Parameter Store, uses presigned S3 URLs to avoid Lambda payload limits, and starts processing from an S3 event.

## Tests

```bash
cd backend
python -m pytest tests -v
```

**Unit tests** (`test_csv_processor.py`) cover the CSV parser:

- A valid file returns all rows.
- A missing required column gives a schema error.
- An invalid email, credit score or age fails only that row.
- An empty file gives a schema error.
- Employment status is normalized to lowercase.
- Files with mixed valid and invalid rows are handled row by row.

**Integration tests** (`test_api.py`) call the running service:

- `GET /health`, `/`, `/users`, `/loan-products` and `/matches`.
- `POST /upload` with a valid CSV, missing columns, a non-CSV file, and mixed rows.

Integration tests skip automatically when the backend is not running.

## Design decisions

**Deterministic SQL for matching.** Eligibility is rules over numbers and categories. An LLM adds cost, latency and non-determinism to a problem that does not need them.

**`notified_at` instead of a notifications table.** A nullable timestamp is enough. `WHERE notified_at IS NULL` selects the work, and setting it after sending prevents duplicates.

**n8n for orchestration.** The assignment specifies self-hosted n8n, which has Postgres, webhook and SMTP nodes built in. Celery or Airflow would mean more code for the same result.

**Upload through the API locally.** `POST /upload` saves the file to a mounted volume and records the logical S3 key in `upload_batches`. In production, presigned URLs send the CSV straight to S3. The boundary is the same and only the transport differs.

**Failure-isolated webhook.** The batch is saved as `completed` before the n8n webhook is called. If n8n is briefly down, the upload still succeeds and can be traced. The request waits up to 10 seconds for the webhook, so this is failure isolation, not fire-and-forget.

## Known limitations

- **The crawler is mocked.** Workflow A uses `/mock/loan-products`, not real bank pages.
- **The LLM is not connected.** The product-normalization step is designed but needs an LLM credential and one extra node in Workflow A.
- **n8n needs memory on Windows.** With under 6 GB allocated to Docker, n8n can restart under load and lose its webhook registrations. 2 GB is enough on Linux.
- **CORS is open.** `allow_origins=["*"]` is for local development. Restrict it to the frontend origin in production.
- **No API authentication.** This is a local demo. Add API keys or OAuth before exposing it.

## What I would do next

1. Add LLM normalization to Workflow A (one node, about 30 lines).
2. Replace the mock catalog with real crawling of 2–3 bank product pages.
3. Add an idempotency key to `POST /upload`, so re-uploading a file returns the same batch ID.
4. Write end-to-end tests that start the stack with `docker compose`, upload a CSV, and verify matches and emails.
5. Move database credentials and the n8n encryption key to SSM Parameter Store or Secrets Manager.
6. Add CloudWatch alarms for webhook failure rate and SES bounce rate.

## Repository layout

```
clickpe-loan-engine/
├── backend/
│   ├── app/
│   │   ├── main.py               FastAPI app, upload endpoint, read APIs
│   │   ├── csv_processor.py      validation rules
│   │   ├── postgres_service.py   database inserts and batch tracking
│   │   ├── n8n_client.py         webhook client
│   │   ├── loan_catalog.py       6-product mock catalog
│   │   ├── emailer.py            SMTP helper
│   │   ├── db.py                 psycopg2 connection pool
│   │   └── config.py             environment config
│   ├── tests/
│   │   ├── test_csv_processor.py
│   │   └── test_api.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   └── index.html                operations dashboard
├── n8n/workflows/                three workflow exports + import guide
├── postgres/init.sql             schema
├── infrastructure/               serverless.yml + local-to-AWS guide
├── data/sample_users.csv         test data
├── uploads/                      CSV landing folder (runtime, gitignored)
├── docs/architecture.md
├── docker-compose.yml
└── README.md
```

## License

Take-home assignment for ClickPe. Not for production use.
