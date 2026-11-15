---
client_industry: real_estate
date: '2022-06-09'
id: fullstack:case:01
project_id: fullstack:p01
provenance: personas@1f579ad2e496
synthetic: true
---

# Mobile backend API for a property management firm

**Situation.** Urbanest's mobile apps talked directly to a spreadsheet and broke weekly.

**Task.** Urbanest needed this fixed within 8 weeks.

**Action.** Designed a set of HTTP endpoints the mobile team consumes, with versioning and docs; stored data in MongoDB with validation and indexes for the hot queries; containerised the service and added health checks.

**Result.** Cut API error rate to under 10%.

**Stack:** node.js, express.js, mongodb, rest api, docker
