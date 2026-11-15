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
