# doc-qa-service

Open-sourced, anonymised version of a project built for a B2B SaaS company (2021).

## Stack
`large language model`, `langchain`, `openai api`, `python`, `postgresql`, `fastapi`

## What it does
Built a retrieval pipeline that grounds every answer in the client's own documents, with citations back to the source page.

## Components
- ingestion pipeline
- chat API
- evaluation report

## Quick start
```bash
docker compose up --build
```

Entry point: `app.py`.

## Results in production
Cut average lookup time from 20 minutes to under 5 seconds.

<!-- synthetic: true; provenance: personas@1f579ad2e496 -->
