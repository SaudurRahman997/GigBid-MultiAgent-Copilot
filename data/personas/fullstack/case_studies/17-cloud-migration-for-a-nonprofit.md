---
client_industry: nonprofit
date: '2026-03-17'
id: fullstack:case:17
project_id: fullstack:p17
provenance: personas@228603469f77
synthetic: true
---

# Cloud migration for a nonprofit

_Open Harvest · nonprofit · 2026-01 · 9 weeks_

Open Harvest's app ran on one ageing server and went down during traffic spikes. I moved the app from a single server to containers on managed cloud with autoscaling. Along the way I set up CI so every merge is tested and deployed automatically, and finally moved the database to a managed Postgres instance with backups.

The result: we reduced hosting cost by 24%.

**Stack:** docker, aws, postgresql, github
