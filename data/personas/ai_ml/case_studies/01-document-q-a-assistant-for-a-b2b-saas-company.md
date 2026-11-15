---
client_industry: saas
date: '2022-01-11'
id: ai_ml:case:01
project_id: ai_ml:p01
provenance: personas@228603469f77
synthetic: true
---

# Document Q&A assistant for a B2B SaaS company

**Situation.** Staff at Orbitdesk spent hours digging through policy PDFs and past case files to answer routine questions.

**Task.** Orbitdesk needed this fixed within 4 weeks.

**Action.** Built a retrieval pipeline that grounds every answer in the client's own documents, with citations back to the source page; chunked and embedded about 20 documents into Postgres with pgvector and added a re-ranking step; wrapped it in a small FastAPI service with a chat front end and an evaluation set of real questions.

**Result.** Cut average lookup time from 20 minutes to under 5 seconds.
