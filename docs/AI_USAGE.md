# AI usage log

Tool: Claude Code (VS Code extension). The student reviews every change, runs the acceptance
checks and approves commits. This log records what the assistant produced and the mistakes we
caught. (Kept honest and updated each phase; required by the assignment.)

| Phase | What the assistant did | Mistake caught | How it was caught / fixed |
|---|---|---|---|
| 1 | Kaggle profiling script | Overlap check reported 0 shared jobs | asaniczka URLs encode `~` as `%7E`; regex fixed, real overlap is 99% |
| 1 | JSONL reader for generated data | `str.splitlines()` split JSON lines on U+2028 inside real job text, crashing the conversation generator | Switched to `split("\n")`; regression test `test_jsonl_roundtrip_survives_unicode_line_separators` |
| 1 | Profile/manifest writers on Windows | Files written with CRLF would break "same seed -> same hashes" across OSes | All writers use `newline="\n"` |
| 1 | Skill extraction | First version treated "business", "website" as skills and dropped real tools (ahrefs, asana) | Data-driven precision filter with a document-frequency floor; seed skills exempt |
| 2 | GigSim FastAPI app | Dependency type alias defined inside the app factory: with `from __future__ import annotations` FastAPI read it as a required query parameter (422 on every call) | Unit tests failed immediately; alias moved to module scope |
| 2 | Simulated client | First calibration hired 73% of tailored proposals (unrealistic, would saturate reply-rate metrics) | Sanity run before committing; bias and hire share recalibrated, calibration test added |
| 3 | Synthetic proposals + BM25 smoke test | Past proposals reused the exact dev-set job wording, so lexical search returned proposals instead of the gold case studies (a leak that would have inflated every RAG metric) | Spotted while smoke-testing the interim retriever; generator now describes past jobs by title/deliverables; check: 0 proposals contain any dev job sentence |
| 3 | PII masking regex | Phone numbers at the end of a sentence ("...900123.") were not masked; card pattern chopped IBANs and wallets | New masking tests; pattern order fixed (specific formats first) |
| 3 | Upwork adapter stub | Used `__getattr__` to stub every method; Python 3.12 `runtime_checkable` Protocols ignore dynamic attributes, so it did not satisfy the port | Port-conformance test failed; methods spelled out explicitly |
| 3 | Single-agent demo (qwen2.5:3b) | Model cited an evidence id it was never given | Citation check in the script flags unknown ids (exit code 2); motivates claim verification (R5) |
| 9 | Trace-id propagation | The analyze route read the job through an MCP client with a fresh random trace id, so that call was not linked to the UI request | The new end-to-end test asserted one trace id across every tool layer and failed; the request's id now lives in a ContextVar used by every MCP client |
| 9 | Injection runner | One local-model call never stopped generating and stalled the whole run | Per-call timeout and an output-token cap; timeouts are recorded separately, never counted as defended |
| 11 | GigSim frozen-hash check | Passed on Windows, failed on Linux CI: `Path` sorting is case-insensitive on Windows | CI showed the failure; sort by POSIX path string, hash re-recorded (ADR 0007) |
| 12 | Extension writer strategy B | "Lead with a quantified result" picked "(2022)" as the number | Read the first trial letters before the full run; years are excluded and a test covers it |
