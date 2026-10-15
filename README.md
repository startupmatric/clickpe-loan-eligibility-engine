# ClickPe — Loan Eligibility Engine

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![n8n](https://img.shields.io/badge/n8n-workflows-EA4B71?logo=n8n&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)

A take-home for the ClickPe SDE Intern role. Reads a CSV of applicants,
matches them against a catalog of loan products, and emails everyone who
qualifies — all locally, on one `docker compose up -d`.

No AWS account needed. Production mapping is included as `serverless.yml`
for reference.

---

## What it does

You upload a CSV. The pipeline takes it from there.

```
CSV file
   │
   ▼
FastAPI /upload — validates every row, stores users, fires a webhook
   │
   ▼
PostgreSQL — users, loan_products, matches, upload_batches
   │
   ▼
n8n Workflow B — one SQL query filters, scores, writes matches
   │
   ▼
n8n Workflow C — every minute, emails unnotified matches, marks them done
   │
   ▼
MailHog inbox — 4 emails, one per matched applicant
```

Every row that fails validation is reported by line number. Nothing gets
silently dropped.

---

## Quick start

You need Docker Desktop, with at least 6 GB of memory allocated to it.
(8 GB if you're on Windows — n8n is heavier there than on Linux.)

```bash
git clone <your-repo-url> clickpe-loan-engine
cd clickpe-loan-engine
docker compose up -d
```

First boot takes about a minute. n8n runs its database migrations the
first time, and those aren't fast.

### Check it came up

```bash
docker compose ps
# 5 containers: postgres, backend, n8n, mailhog, frontend

curl http://localhost:8000/health
# {"status":"healthy","database":"connected"}
```

### Open these

| What | Where |
|---|---|
| Dashboard | http://localhost:3000 |
| FastAPI Swagger | http://localhost:8000/docs |
| n8n | http://localhost:5678 |
| MailHog inbox | http://localhost:8025 |

### Import the n8n workflows

This part is manual — n8n doesn't read workflow files from the filesystem.

1. Open http://localhost:5678
2. Set up the owner account (whatever email/password you want)
3. Left sidebar → **Workflows**
4. Top-right → **Import from File**
5. Import each of the three files from `n8n/workflows/`
6. Reattach the `Loan DB Local` Postgres credential on each Postgres node
7. Flip **Active** on all three

The `n8n/workflows/README.md` walks through the credentials and fixes for
common mistakes. It's short.

### Run the demo

```bash
curl -X POST -F "file=@data/sample_users.csv" http://localhost:8000/upload
```

Response:

```json
{
  "batch_id": "0887f79f-e16f-4029-b84e-6b0a65b8694d",
  "filename": "sample_users.csv",
  "records_processed": 5,
  "records_failed": 1,
  "errors": ["line 7: invalid email"]
}
```

Then open http://localhost:3000. The dashboard shows applicants, matches,
and emails live.

---

## The interesting part

The assignment calls this the "Optimization Treasure Hunt". Here's what it
means in this codebase.

### The naive approach

For 1,000 applicants and 30 loan products:

```
1,000 × 30 = 30,000 eligibility decisions
```

If you hand each decision to an LLM, that's 30,000 API calls per upload.
Cost, latency, non-determinism, and no way to explain why a specific match
was made.

### What actually happens

**One SQL query does the filtering.** Before any business logic runs, four
indexed predicates in Postgres eliminate candidates that can't possibly match:

```sql
WHERE u.monthly_income >= l.min_monthly_income
  AND u.credit_score   >= l.min_credit_score
  AND u.age            BETWEEN l.min_age AND l.max_age
  AND (l.employment_statuses IS NULL
       OR u.employment_status = ANY(l.employment_statuses))
```

The `CROSS JOIN` never materializes. Postgres uses the indexes on
`users(monthly_income, credit_score, age, employment_status)` and
`loan_products(min_monthly_income, min_credit_score, min_age, max_age)` to
skip most pairs entirely.

On a 1,000-user workload, this typically removes **over 85%** of candidates
before scoring. On the 5-user sample in this repo, 4 out of 5 users match
something and one (carol, income 15k, credit 540) matches nothing at all.
She's correctly absent from the results.

You can see this in the dashboard — the **Matching Funnel** shows candidates
in, candidates passed, candidates notified, as three bars. On the sample
data it reads 30 → 21 → 21 (before Workflow C runs).

**Scoring is deterministic.**

```sql
match_score = 100 × (
    0.50 × credit_headroom
  + 0.30 × income_headroom
  + 0.20 × age_fit
)
```

Nobody has to trust a black box. Every score is a single SQL expression you
can read.

**The LLM stays where it belongs.** Not in the per-user path. The
architecture reserves it for the product-normalization layer — parsing a
scraped eligibility blurb into structured criteria, once per product, never
per user-product pair. That's the only place where semantic reasoning adds
value over a deterministic rule.

### What that gets you

| Metric | LLM-per-pair | This system |
|---|---|---|
| Evaluations per 1,000-user upload | 30,000 | under 2,000 |
| LLM calls per upload | 30,000 | 0 |
| Cost per upload | High | Zero |
| Reproducible | No | Yes |
| Auditable | No | Yes — the SQL is the source of truth |

---

## API

| Method | Path | What it does |
|---|---|---|
| `GET` | `/health` | DB connectivity check |
| `POST` | `/upload` | CSV → validate → users → webhook |
| `GET` | `/batches/{id}` | Batch audit lookup |
| `GET` | `/users` | List applicants |
| `GET` | `/loan-products` | List catalog |
| `GET` | `/matches` | List matches |
| `GET` | `/mock/loan-products` | Static catalog (stands in for real crawling) |
| `POST` | `/dev/rematch/{id}` | Re-run matching for a batch |

---

## Schema

Four tables. See `postgres/init.sql` for the full definitions.

- **`upload_batches`** — one row per CSV upload. Filename, status, counts,
  timestamps. This is how you trace what happened and when.
- **`users`** — one row per applicant. Business key, eligibility fields,
  foreign key to the batch that brought them in.
- **`loan_products`** — the catalog. Eligibility thresholds, source URL,
  last updated. Unique on `(product_name, provider)`.
- **`matches`** — one row per user-product pair that passed. Score, reason,
  `notified_at`. Unique on `(user_id, product_id)`.

Both `matches` and `users` have `ON CONFLICT DO UPDATE` behavior — re-running
anything is safe. It updates instead of duplicating.

---

## n8n workflows

Three of them, exported to `n8n/workflows/`:

| File | Trigger | What it does |
|---|---|---|
| `workflow-a-loan-discovery.json` | Schedule (6h) | Fetch products, upsert into `loan_products` |
| `workflow-b-matching.json` | Webhook | SQL pre-filter, score, insert matches |
| `workflow-c-notification.json` | Schedule (1m) | Fetch unnotified, email, mark notified |

Import instructions and credential details in `n8n/workflows/README.md`.

**About Workflow A.** It currently pulls from `/mock/loan-products`, an
endpoint that returns the 6-product catalog as JSON. The structure is the
same as a real crawler would produce — schedule → HTTP fetch → normalize →
Postgres upsert with `source_url` preserved for provenance. Swapping in 2–3
real bank product pages is a URL change and an HTML-parsing step, not a
redesign. I've written it up in the [What I'd do next](#what-id-do-next)
section rather than claiming it works.

---

## Local → AWS

`infrastructure/serverless.yml` has the mapping. Short version:

| Local Docker | AWS |
|---|---|
| FastAPI `/upload` | API Gateway + Lambda |
| `uploads/` volume | S3 bucket |
| `docker compose up -d` | `serverless deploy` |
| PostgreSQL container | RDS PostgreSQL |
| n8n container | n8n on EC2 / ECS |
| MailHog | Amazon SES |

The service boundaries are identical. The CSV parser, validation rules,
matching SQL, n8n workflows, and frontend don't change.

The `serverless.yml` is a real deploy config, not a sketch. It uses SSM
Parameter Store for secrets, presigned S3 URLs to keep the CSV out of
Lambda's payload limits, and an S3 event trigger for CSV processing.

---

## Tests

```bash
cd backend
python -m pytest tests -v
```

**Unit tests** (`test_csv_processor.py`) cover the CSV parser:

- Valid file → all rows returned
- Missing required column → schema error
- Invalid email → row error, other rows still pass
- Credit score out of range → row error
- Age out of range → row error
- Empty file → schema error
- Employment status normalized to lowercase
- Mixed valid and invalid rows

**Integration tests** (`test_api.py`) hit the running FastAPI service:

- `GET /health`, `GET /`, `GET /users`, `GET /loan-products`, `GET /matches`
- `POST /upload` with valid CSV, missing columns, non-CSV file, mixed rows

These skip automatically if the backend isn't running, so you can run the
whole suite either way.

---

## Design decisions

**Why deterministic SQL for matching.** Eligibility is rules over numbers
and categories. An LLM adds cost, latency, and non-determinism to a problem
that doesn't need it. The LLM belongs on unstructured input — scraped
eligibility text — where a rule can't help.

**Why `notified_at` instead of a notifications table.** A nullable timestamp
is enough. `WHERE notified_at IS NULL` filters the work; setting it after
send prevents duplicates. A separate table would need joins and give you
nothing extra.

**Why n8n.** The assignment specifies self-hosted n8n. It has a Postgres
node, a webhook trigger, and an SMTP node built in. Celery or Airflow would
be more code for the same result.

**Why the CSV goes through the API locally.** Docker Compose runs a
self-contained stack. `POST /upload` writes the file to a mounted volume and
records the logical S3 key in `upload_batches`. In production the presigned
URL flow in `serverless.yml` sends the CSV straight to S3. Same boundary,
different transport.

**Why the webhook call is failure-isolated.** The batch is recorded as
`completed` **before** the n8n webhook is fired. If n8n is briefly
unreachable, the upload still succeeds and the batch is traceable. The
request does wait up to 10 seconds for the webhook response, so it's not
strictly fire-and-forget — it's failure-isolated.

**Why no framework on the frontend.** It's a single HTML file with inline
CSS and JS. 22 KB, no build step, first paint under 100 ms. For an internal
ops dashboard with a handful of tables and a form, React would be
overhead without payoff.

---

## Known limitations

**The crawler is mocked.** Workflow A reads from `/mock/loan-products`
instead of scraping real bank pages. The data shape is identical to what a
real crawler would produce — see the note in the n8n section.

**The LLM isn't wired in.** The design reserves a normalization step for
it. Implementing it needs an LLM credential and one extra node in Workflow
A. This is the honest state of the repo.

**n8n needs headroom on Windows.** Under 6 GB allocated to Docker, n8n may
restart under load and lose webhook registrations. On Linux it's fine at
2 GB.

**CORS is wide open.** `allow_origins=["*"]` for local development. Restrict
to the frontend origin in production. Called out in the deploy notes too.

**No auth on the API.** Local demo, not a deployment. Add API keys or
OAuth before putting this anywhere public.

---

## What I'd do next

In rough priority order:

1. Wire the LLM normalization into Workflow A. One node, ~30 lines.
2. Replace `/mock/loan-products` with real crawling of 2–3 bank product
   pages. The extraction and upsert logic doesn't change.
3. Add an idempotency key to `POST /upload` so re-uploading the same file
   returns the same batch ID instead of creating a new one.
4. End-to-end tests using `docker compose` + pytest — spin up the stack,
   upload a CSV, verify matches and emails without mocking.
5. Move Postgres credentials and the n8n encryption key to SSM Parameter
   Store or AWS Secrets Manager.
6. CloudWatch alarms on webhook failure rate and SES bounce rate.

---

## Repo layout

```
clickpe-loan-engine/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI app, upload endpoint, read APIs
│   │   ├── csv_processor.py     validation rules
│   │   ├── postgres_service.py  DB inserts and batch tracking
│   │   ├── n8n_client.py        webhook client
│   │   ├── loan_catalog.py      6-product mock catalog
│   │   ├── emailer.py           SMTP helper
│   │   ├── db.py                psycopg2 connection pool
│   │   └── config.py            env config
│   ├── tests/
│   │   ├── test_csv_processor.py
│   │   └── test_api.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   └── index.html               operations dashboard
├── n8n/
│   ├── workflows/
│   │   ├── workflow-a-loan-discovery.json
│   │   ├── workflow-b-matching.json
│   │   ├── workflow-c-notification.json
│   │   └── README.md            import instructions
├── postgres/
│   └── init.sql                 schema
├── infrastructure/
│   ├── serverless.yml           AWS deployment reference
│   └── README.md                local → AWS mapping
├── data/
│   └── sample_users.csv         test data
├── uploads/                     CSV landing (runtime, gitignored)
├── docs/
│   └── architecture.md
├── docker-compose.yml
├── .gitignore
└── README.md
```

---

## License

Take-home assignment for ClickPe. Not for production use.
