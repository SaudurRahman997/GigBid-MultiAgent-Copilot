---
client_industry: hospitality
date: '2026-01-11'
id: fullstack:case:14
project_id: fullstack:p14
provenance: personas@1f579ad2e496
synthetic: true
---

# Subscription billing for a boutique hotel group

**Situation.** Harbourline Stays invoiced subscribers by hand at the end of each month.

**Task.** Harbourline Stays needed this fixed within 9 weeks.

**Action.** Integrated a payments provider for subscriptions, upgrades and failed-payment retries; wrote webhook handlers with idempotency keys so retries never double-charge; deployed on managed cloud functions with alerting.

**Result.** Recovered 18% of failed payments automatically.

**Stack:** api integration, node.js, typescript, aws
