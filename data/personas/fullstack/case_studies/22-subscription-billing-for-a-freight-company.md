---
client_industry: logistics
date: '2026-10-19'
id: fullstack:case:22
project_id: fullstack:p22
provenance: personas@1f579ad2e496
synthetic: true
---

# Subscription billing for a freight company

**Situation.** Haulwise invoiced subscribers by hand at the end of each month.

**Task.** Haulwise needed this fixed within 12 weeks.

**Action.** Integrated a payments provider for subscriptions, upgrades and failed-payment retries; wrote webhook handlers with idempotency keys so retries never double-charge; deployed on managed cloud functions with alerting.

**Result.** Recovered 12% of failed payments automatically.

**Stack:** api integration, node.js, typescript, aws
