---
version: 1
name: answer_screening_question
inputs: [question]
---
Answer this client screening question using ONLY my portfolio evidence.

Question: {question}

Steps:
1. Call `search_evidence` with the question (k=5) and read the returned snippets.
2. Answer in 3-5 sentences, first person, plain language.
3. After each factual claim, cite the evidence id in brackets, e.g. [ai_ml:case:03].
4. If no evidence supports an answer, say so honestly instead of inventing experience.
