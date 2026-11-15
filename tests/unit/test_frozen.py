"""The gigsim freeze check detects any content change and ignores caches."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "check_gigsim_frozen",
    Path(__file__).resolve().parents[2] / "scripts" / "check_gigsim_frozen.py",
)
frozen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frozen)


def test_tree_hash_changes_with_content_not_with_caches(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    h1 = frozen.tree_hash(tmp_path)
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"junk")
    (tmp_path / "local.db").write_bytes(b"sqlite")
    assert frozen.tree_hash(tmp_path) == h1
    (tmp_path / "a.py").write_text("x = 2\n")
    assert frozen.tree_hash(tmp_path) != h1


def test_tree_hash_ignores_line_endings(tmp_path):
    (tmp_path / "a.py").write_bytes(b"x = 1\n")
    h1 = frozen.tree_hash(tmp_path)
    (tmp_path / "a.py").write_bytes(b"x = 1\r\n")
    assert frozen.tree_hash(tmp_path) == h1


def test_repo_gigsim_matches_recorded_hash():
    assert frozen.FROZEN.exists(), "run scripts/check_gigsim_frozen.py --update"
    assert frozen.tree_hash() == frozen.FROZEN.read_text().strip()
