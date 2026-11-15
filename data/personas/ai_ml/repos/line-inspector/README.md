# line-inspector

Open-sourced, anonymised version of a project built for a property management firm (2026).

## Stack
`computer vision`, `pytorch`, `opencv`, `python`, `docker`

## What it does
Trained a model spotting scratches and dents in production-line camera images.

## Components
- detection model
- edge deployment
- labelling set

## Quick start
```bash
docker compose up --build
```

Entry point: `infer.py`.

## Results in production
Caught 58% of defects at the line.

<!-- synthetic: true; provenance: personas@228603469f77 -->
