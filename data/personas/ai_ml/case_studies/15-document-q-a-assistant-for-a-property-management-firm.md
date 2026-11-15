---
client_industry: real_estate
date: '2026-02-25'
id: ai_ml:case:15
project_id: ai_ml:p15
provenance: personas@1f579ad2e496
synthetic: true
---

# Document Q&A assistant for a property management firm

_Oakrow Properties · property management firm · 2026-01 · 4 weeks_

Staff at Oakrow Properties spent hours digging through policy PDFs and past case files to answer routine questions. I built a retrieval pipeline that grounds every answer in the client's own documents, with citations back to the source page. Along the way I chunked and embedded about 1200 documents into Postgres with pgvector and added a re-ranking step, and finally wrapped it in a small FastAPI service with a chat front end and an evaluation set of real questions.

The result: we answered 28% of internal questions without escalation.
