---
client_industry: healthcare
date: '2025-05-22'
id: ai_ml:case:12
project_id: ai_ml:p12
provenance: personas@1f579ad2e496
synthetic: true
---

# Support ticket triage for a clinic network

**Client:** Pinecrest Health (clinic network)  
**When:** 2025-03, 8 weeks

## Challenge
Pinecrest Health's support inbox mixed billing, bugs and sales questions, and urgent tickets waited for hours.

## What I did
- Trained a transformer classifier routing free-text tickets to the right queue
- Labelled 1200 historical tickets with the support leads and measured agreement
- Deployed it behind the helpdesk webhook with a fallback to manual triage

## Outcome
Routed 50% of tickets correctly without human review.
