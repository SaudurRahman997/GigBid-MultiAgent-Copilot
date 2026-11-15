---
client_industry: real_estate
date: '2024-12-06'
id: ai_ml:case:08
project_id: ai_ml:p08
provenance: personas@228603469f77
synthetic: true
---

# Scheduling assistant agent for a property management firm

_Keystone Lettings · property management firm · 2024-07 · 20 weeks_

Coordinators at Keystone Lettings spent half their day on back-and-forth emails to book meetings. I built an assistant that calls the calendar and CRM tools on its own to propose and book slots. Along the way I added guardrails so it asks a human before sending anything external, and finally logged every tool call for audit and replay.

The result: we saved coordinators about 120 hours a week.

**Stack:** ai agent development, langchain, openai api, python
