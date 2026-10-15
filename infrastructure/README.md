# Infrastructure

This folder is the AWS version of the local Docker setup.

You do **not** need an AWS account to run the take-home. The demo runs locally.

## Local vs AWS

| Local | AWS |
|---|---|
| FastAPI | Lambda |
| `uploads/` | S3 |
| PostgreSQL | RDS PostgreSQL |
| n8n | EC2 / ECS |
| MailHog | Amazon SES |

## AWS flow

```text
Browser
   |
   v
API Gateway
   |
   v
Lambda
   |
   v
S3
   |
   v
Lambda processes CSV
   |
   +----> RDS PostgreSQL
   |
   +----> n8n webhook
             |
             v
            SES
```

The local flow is almost the same. The main difference is that AWS uses S3 for the CSV upload and Lambda for processing.

## What stays the same

- PostgreSQL schema
- Matching SQL
- n8n workflows
- Frontend
- CSV validation
- Notification flow

So the AWS setup is mainly a deployment change, not a new application.

## AWS deployment

This is included as a reference. It is not required for the local demo.

You would need:

- AWS account
- Serverless Framework
- RDS PostgreSQL
- S3
- SES
- n8n running on EC2 or ECS
- SSM parameters for the database URL, n8n webhook and SES sender

Example:

```bash
cd infrastructure
serverless deploy --stage dev
```

## One important note

The AWS handlers referenced in `serverless.yml` are deployment wrappers.

The local application currently runs through FastAPI and Docker.

If the project is deployed to AWS later, the Lambda wrapper functions would need to be added around the existing backend logic.

For this take-home, the local Docker setup is the actual demo.
