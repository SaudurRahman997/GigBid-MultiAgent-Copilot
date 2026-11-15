---
client_industry: healthcare
date: '2022-03-19'
id: data_analyst:case:02
project_id: data_analyst:p02
provenance: personas@228603469f77
synthetic: true
---

# Data pipeline into a warehouse for a clinic network

_Brightwater Clinics · clinic network · 2022-01 · 7 weeks_

Brightwater Clinics's data lived in five tools and every report started with manual exports. I wrote scheduled jobs that pull data from each tool, clean it and load it into one warehouse. Along the way I modelled the tables so analysts can write simple queries, and finally added row-count and freshness checks with alerts.

The result: we removed 5 manual exports a week.
