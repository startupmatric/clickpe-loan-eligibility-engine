# n8n Workflows

Three workflows power the loan eligibility pipeline. Import them once, configure the local credentials, activate them, and the pipeline runs automatically.

## How to import

1. Open `http://localhost:5678`
2. Complete the n8n owner account setup if you have not already.
3. Open **Workflows** from the left sidebar.
4. Select **Import from File**.
5. Import each JSON workflow.
6. Configure the credentials described below.
7. Toggle each workflow to **Active**.

## The files

| File | What it does | Trigger |
|---|---|---|
| `workflow-a-loan-discovery.json` | Retrieves the loan-product catalog and prepares products for persistence in `loan_products` | Schedule |
| `workflow-b-matching.json` | Runs the SQL pre-filter and deterministic scoring, then writes results into `matches` | Webhook — `POST /webhook/ingest-complete` |
| `workflow-c-notification.json` | Sends one email per user for unnotified matches and records `notified_at` | Schedule — every minute |

> **Important:** Workflow A in the current JSON export retrieves products from the local backend endpoint `/mock/loan-products` and splits the products for downstream processing. The current export does **not** contain a PostgreSQL UPSERT node. If you add the persistence node, use the `Loan DB Local` credential described below.

## Credentials

### PostgreSQL — `Loan DB Local`

Use this credential for PostgreSQL nodes:

| Field | Value |
|---|---|
| Host | `postgres` |
| Port | `5432` |
| Database | `loan_db` |
| User | `loan_user` |
| Password | `loan_password` |
| SSL | `disable` |

**Important:** The host is `postgres`, not `localhost`.

Inside Docker, `postgres` is the Docker Compose service name. `localhost` would refer to the n8n container itself.

If an imported workflow shows a PostgreSQL credential named **Postgres account**, replace/rebind it to **Loan DB Local**.

### SMTP — MailHog

Workflow C uses MailHog for the local demo instead of AWS SES.

| Field | Value |
|---|---|
| Host | `mailhog` |
| Port | `1025` |
| SSL/TLS | Off |
| User | Leave blank |
| Password | Leave blank |

**Important:** The host is `mailhog`, not `localhost`.

MailHog's web inbox is available at:

`http://localhost:8025`

For the take-home demo, use only test inbox aliases/addresses. Do not send emails to real sample-user addresses.

## Workflow A — Loan Product Discovery

The workflow is intended to run on a schedule and:

1. Request the loan-product catalog.
2. Normalize the returned product objects.
3. Split products into individual records.
4. Persist/upsert normalized products into `loan_products` when the PostgreSQL persistence node is present.

The current local demo source is:

```text
http://backend:8000/mock/loan-products
```

This keeps the local demo deterministic and avoids depending on external websites during the walkthrough.

## Workflow B — User-Loan Matching

Workflow B is triggered by:

```text
POST /webhook/ingest-complete
```

The backend sends the completed upload batch ID to n8n after users have been persisted.

The workflow then:

1. Validates the batch UUID.
2. Uses a SQL `CROSS JOIN` to generate candidate user/product pairs.
3. Applies deterministic eligibility predicates for:
   - monthly income
   - credit score
   - age
   - employment status
4. Scores only the candidates that survive the SQL pre-filter.
5. Inserts matching records into `matches`.
6. Uses a unique user/product constraint to keep matching idempotent.
7. Returns a webhook response.

### Optimization principle

The matching workflow intentionally avoids sending every user/product pair to an LLM.

Example:

```text
10,000 users × 30 products
        ↓
300,000 possible pairs
        ↓
SQL eligibility pre-filter
        ↓
~2,000 candidates
        ↓
Deterministic scoring
        ↓
Optional AI enrichment only when needed
```

This makes the core matching path deterministic, cheaper, faster, and easier to audit.

## Workflow C — User Notification

Workflow C periodically looks for matches where:

```sql
notified_at IS NULL
```

It groups matches by user, creates one personalized email containing the user's new loan matches, sends it through MailHog, and then records the notification timestamp.

This makes the notification step idempotent: already-notified matches are not sent again.

## End-to-end flow

```text
CSV Upload
    ↓
FastAPI
    ↓
PostgreSQL users
    ↓
POST /webhook/ingest-complete
    ↓
n8n Workflow B
    ↓
SQL pre-filter + deterministic scoring
    ↓
PostgreSQL matches
    ↓
n8n Workflow C
    ↓
MailHog
    ↓
http://localhost:8025
```

## After activating

1. Upload a CSV through the FastAPI UI/API.
2. FastAPI validates and persists the users.
3. FastAPI triggers the n8n matching webhook.
4. Workflow B creates eligible matches.
5. Workflow C runs on its schedule.
6. Open MailHog at `http://localhost:8025` to see the demo emails.

No manual matching step is required after the upload.

## Troubleshooting

### Webhook returns 404

Workflow B is probably not active.

Open Workflow B in n8n and make sure the **Active** toggle is enabled.

You can also check:

```sql
SELECT name, active
FROM workflow_entity;
```

### PostgreSQL node has a red triangle

The credential is missing or not attached.

Open the node and select:

```text
Loan DB Local
```

Make sure the host is:

```text
postgres
```

not:

```text
localhost
```

### Workflow cannot be activated

n8n normally refuses to activate a workflow when a node has a missing credential.

Open the affected node, attach the correct credential, save, and activate again.

### Emails do not appear

Workflow C runs every minute in the local demo.

Check:

```text
http://localhost:8025
```

If the inbox is empty:

1. Open n8n.
2. Go to **Executions**.
3. Open the latest Workflow C execution.
4. Find the node that failed.
5. Verify the MailHog SMTP credential.
6. Verify the SMTP host is `mailhog` and port is `1025`.

### Backend webhook does not trigger Workflow B

From inside the Docker network, the backend should use:

```text
http://n8n:5678/webhook/ingest-complete
```

Do not use `localhost` from inside the backend container.

## Local service URLs

| Service | URL |
|---|---|
| FastAPI | http://localhost:8000 |
| FastAPI docs | http://localhost:8000/docs |
| n8n | http://localhost:5678 |
| MailHog | http://localhost:8025 |
| PostgreSQL | localhost:5432 |

## AWS mapping

The local Docker setup mirrors the intended AWS architecture:

| Local | AWS-ready equivalent |
|---|---|
| FastAPI container | Lambda |
| PostgreSQL container | RDS PostgreSQL |
| Local uploads volume | S3 |
| FastAPI HTTP endpoint | API Gateway |
| MailHog | AWS SES |
| n8n container | Self-hosted n8n |

The local setup is intentionally used for the take-home demo so the entire system can run without an AWS account or cloud spend.
