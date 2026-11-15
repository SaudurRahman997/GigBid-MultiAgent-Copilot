---
client_industry: saas
date: '2025-09-26'
id: ai_ml:case:14
project_id: ai_ml:p14
provenance: personas@228603469f77
synthetic: true
---

# Invoice and receipt extraction for a B2B SaaS company

**Situation.** The finance team at Tallyhq keyed in hundreds of scanned invoices by hand every week.

**Task.** Tallyhq needed this fixed within 15 weeks.

**Action.** Built a pipeline reading scanned invoices and pulling out totals, dates, vendors and line items; fine-tuned a layout-aware model in PyTorch on 120 labelled pages; added confidence thresholds so uncertain fields go to a human.

**Result.** Processed 120 invoices a day at 19% field accuracy.

**Stack:** computer vision, natural language processing, pytorch, python, aws
