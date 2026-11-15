# ticket-classifier-manufacturing

Open-sourced, anonymised version of a project built for an auto-parts manufacturer (2022).

## Stack
`natural language processing`, `hugging face`, `pytorch`, `python`

## What it does
Trained a transformer classifier routing free-text tickets to the right queue.

## Components
- classifier
- webhook integration
- labelling guide

## Quick start
```bash
docker compose up --build
```

Entry point: `evaluate.py`.

## Results in production
Routed 33% of tickets correctly without human review.

<!-- synthetic: true; provenance: personas@1f579ad2e496 -->
