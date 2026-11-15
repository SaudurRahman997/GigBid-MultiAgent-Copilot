---
client_industry: real_estate
date: '2026-11-14'
id: ai_ml:case:18
project_id: ai_ml:p18
provenance: personas@228603469f77
synthetic: true
---

# Visual defect detection for a property management firm

**Situation.** Inspectors at Oakrow Properties missed small scratches on parts during busy shifts.

**Task.** Oakrow Properties needed this fixed within 15 weeks.

**Action.** Trained a model spotting scratches and dents in production-line camera images; collected and labelled 5 images with the quality team, including hard edge cases; packaged it in Docker to run on the line's edge PC.

**Result.** Caught 58% of defects at the line.

**Stack:** computer vision, pytorch, opencv, python, docker
