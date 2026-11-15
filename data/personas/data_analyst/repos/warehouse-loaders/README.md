# warehouse-loaders

Open-sourced, anonymised version of a project built for a clinic network (2022).

## Stack
`etl`, `sql`, `python`, `bigquery`

## What it does
Wrote scheduled jobs that pull data from each tool, clean it and load it into one warehouse.

## Components
- pipelines
- warehouse model
- data checks

## Quick start
```bash
docker compose up --build
```

Entry point: `load_crm.py`.

## Results in production
Removed 5 manual exports a week.

<!-- synthetic: true; provenance: personas@228603469f77 -->
