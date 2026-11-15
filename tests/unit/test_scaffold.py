"""Phase 0 smoke tests: repo layout, config and the prompt checker."""

from pathlib import Path

import yaml

from scripts.check_prompts import scan_file

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_PATHS = [
    "agent/config.yaml",
    "agent/prompts",
    "agent/graphs",
    "agent/nodes",
    "agent/memory",
    "mcp_servers/portfolio",
    "mcp_servers/marketplace/adapters",
    "mcp_servers/workspace",
    "rag/ingest",
    "rag/variants",
    "gigsim/policy",
    "apps/api/routers",
    "apps/web/package.json",
    "evals/runners",
    "evals/results",
    "data/generators",
    "data/policy_pack",
    "tests/contract",
    "infra/docker-compose.yml",
    "docs/adr",
    ".env.example",
    "CLAUDE.md",
]


def test_required_paths_exist():
    missing = [p for p in REQUIRED_PATHS if not (ROOT / p).exists()]
    assert not missing, f"missing: {missing}"


def test_config_has_core_keys_and_never_auto_sends():
    cfg = yaml.safe_load((ROOT / "agent/config.yaml").read_text(encoding="utf-8"))
    for key in ("marketplace", "profile", "profiles", "nodes", "rag", "budgets", "autonomy"):
        assert key in cfg, key
    assert cfg["marketplace"] in {"gigsim", "upwork_live"}
    assert cfg["autonomy"]["auto_send"] is False
    roles = set(cfg["profiles"][cfg["profile"]])
    assert set(cfg["nodes"].values()) <= roles


def test_env_example_has_no_real_secrets():
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            if any(s in key for s in ("KEY", "SECRET", "TOKEN", "PASSWORD")):
                assert value in {"", "change-me"}, key


def test_prompt_checker_flags_hardcoded_prompt(tmp_path):
    bad = tmp_path / "node.py"
    bad.write_text('P = "You are a helpful proposal writer. ' + "x" * 150 + '"\n', encoding="utf-8")
    assert scan_file_rel(bad)


def test_prompt_checker_allows_docstrings_and_short_strings(tmp_path):
    ok = tmp_path / "node.py"
    ok.write_text(
        '"""You are reading a module docstring ' + "x" * 150 + '"""\nA = "short"\n',
        encoding="utf-8",
    )
    assert not scan_file_rel(ok)


def scan_file_rel(path: Path) -> list[str]:
    # scan_file reports paths relative to the repo root; patch ROOT for tmp files.
    import scripts.check_prompts as cp

    old = cp.ROOT
    cp.ROOT = path.parent
    try:
        return scan_file(path)
    finally:
        cp.ROOT = old


def test_prompt_checker_file_exemption_needs_reason(tmp_path):
    body = 'P = "You are a helpful proposal writer. ' + "x" * 150 + '"\n'
    with_reason = tmp_path / "a.py"
    with_reason.write_text(
        "# prompt-ok-file: attack strings used as test data\n" + body, encoding="utf-8"
    )
    no_reason = tmp_path / "b.py"
    no_reason.write_text("# prompt-ok-file:\n" + body, encoding="utf-8")
    assert not scan_file_rel(with_reason)
    assert scan_file_rel(no_reason)
