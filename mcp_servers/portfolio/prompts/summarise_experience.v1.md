---
version: 1
name: summarise_experience
inputs: [skill]
---
Summarise my experience with **{skill}** for a client.

1. Call `search_evidence` with "{skill}" (k=8), then `get_case_study` for the two strongest case studies.
2. Write 4-6 bullet points: what I built, for which kind of client, and the measured result.
3. Cite an evidence id on every bullet, e.g. [fullstack:case:07]. Skills may be implied rather than
   named in the evidence - say "built X (uses {skill})" only when the evidence clearly shows it.
4. No guarantees, no numbers that are not in the evidence.
