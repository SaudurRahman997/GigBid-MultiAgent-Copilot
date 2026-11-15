---
client_industry: manufacturing
date: '2022-07-06'
id: ai_ml:case:02
project_id: ai_ml:p02
provenance: personas@1f579ad2e496
synthetic: true
---

# Support ticket triage for an auto-parts manufacturer

**Client:** Castwell (auto-parts manufacturer)  
**When:** 2022-06, 5 weeks

## Challenge
Castwell's support inbox mixed billing, bugs and sales questions, and urgent tickets waited for hours.

## What I did
- Trained a transformer classifier routing free-text tickets to the right queue
- Labelled 15 historical tickets with the support leads and measured agreement
- Deployed it behind the helpdesk webhook with a fallback to manual triage

## Outcome
Routed 33% of tickets correctly without human review.
