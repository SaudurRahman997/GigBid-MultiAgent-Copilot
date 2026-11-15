---
client_industry: logistics
date: '2024-11-07'
id: ai_ml:case:10
project_id: ai_ml:p10
provenance: personas@1f579ad2e496
synthetic: true
---

# Invoice and receipt extraction for a freight company

_Ridgeway Freight · freight company · 2024-09 · 8 weeks_

The finance team at Ridgeway Freight keyed in hundreds of scanned invoices by hand every week. I built a pipeline reading scanned invoices and pulling out totals, dates, vendors and line items. Along the way I fine-tuned a layout-aware model in PyTorch on 5 labelled pages, and finally added confidence thresholds so uncertain fields go to a human.

The result: we processed 5 invoices a day at 25% field accuracy.
