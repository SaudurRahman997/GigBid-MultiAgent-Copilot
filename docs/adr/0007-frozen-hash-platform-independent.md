# ADR 0007: GigSim frozen hash, platform-independent file order

Status: accepted (2026-11-17)

## Context

`scripts/check_gigsim_frozen.py` hashes every file under `gigsim/` and compares the result with
`gigsim/FROZEN.sha256`. It passed on the Windows dev machine but failed in CI (Ubuntu) on every
push, although no GigSim file had changed.

Cause: the files were sorted as `Path` objects. On Windows, `Path` ordering is case-insensitive;
on Linux it is case-sensitive. `README.md` sorted among the lowercase file names on Windows and
first on Linux, so the two platforms hashed the same bytes in a different order.

## Decision

Sort by the relative POSIX path string, which orders the same way on every platform, and record the
new hash once with `--update`.

## What changed

- `scripts/check_gigsim_frozen.py`: sort key only.
- `gigsim/FROZEN.sha256`: `44ba37e5...` -> `79dc40f5...`.
- No file of GigSim itself changed (`git diff HEAD -- gigsim ':!gigsim/FROZEN.sha256'` is empty), so
  all GigSim-based results stay comparable.
