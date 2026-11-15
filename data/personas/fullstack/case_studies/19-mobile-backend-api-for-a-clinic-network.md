---
client_industry: healthcare
date: '2026-09-19'
id: fullstack:case:19
project_id: fullstack:p19
provenance: personas@228603469f77
synthetic: true
---

# Mobile backend API for a clinic network

**Situation.** Brightwater Clinics's mobile apps talked directly to a spreadsheet and broke weekly.

**Task.** Brightwater Clinics needed this fixed within 20 weeks.

**Action.** Designed a set of HTTP endpoints the mobile team consumes, with versioning and docs; stored data in MongoDB with validation and indexes for the hot queries; containerised the service and added health checks.

**Result.** Cut API error rate to under 10%.

**Stack:** node.js, express.js, mongodb, rest api, docker
