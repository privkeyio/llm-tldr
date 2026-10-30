"""A checked-out repo must not be able to run code or steer tools through tldr."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import tldr
from tldr import mcp_server


def _shadow_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "tldr").mkdir(parents=True)
    (repo / "tldr" / "__init__.py").write_text("")
    (repo / "tldr" / "cli.py").write_text('print("SHADOWED")\n')
    return repo


def test_daemon_launch_ignores_repo_modules(tmp_path, monkeypatch):
    repo = _shadow_repo(tmp_path)
    monkeypatch.chdir(repo)
    captured = []

    def fake_popen(argv, **kwargs):
        captured.append(argv)
        raise RuntimeError("stop")

    monkeypatch.setattr(mcp_server, "_ping_daemon", lambda project: False)
    monkeypatch.setattr(mcp_server.subprocess, "Popen", fake_popen)
    with pytest.raises(RuntimeError, match="stop"):
        mcp_server._ensure_daemon(str(repo))
    monkeypatch.undo()

    argv = captured[0][:4] + ["--help"]
    result = subprocess.run(argv, cwd=repo, capture_output=True, text=True, timeout=60)
    assert "SHADOWED" not in result.stdout
    assert "usage: tldr" in result.stdout
    unsafe = subprocess.run([sys.executable, "-m", "tldr.cli"], cwd=repo, capture_output=True, text=True)
    assert "SHADOWED" in unsafe.stdout


def test_every_python_launch_uses_helper():
    pkg = Path(tldr.__file__).parent
    for src in pkg.rglob("*.py"):
        if src.name != "_launch.py":
            assert "sys.executable" not in src.read_text(), src


def test_bootstrap_ignores_repo_modules(tmp_path):
    from tldr._launch import _BOOTSTRAP

    repo = _shadow_repo(tmp_path)
    (repo / "runpy.py").write_text('print("SHADOWED")\n')
    argv = [sys.executable, "-c", _BOOTSTRAP, "tldr.cli", "--help"]
    result = subprocess.run(argv, cwd=repo, capture_output=True, text=True, timeout=60)
    assert "SHADOWED" not in result.stdout
    assert "usage: tldr" in result.stdout


@pytest.fixture
def daemon(tmp_path, monkeypatch):
    from tldr.daemon import TLDRDaemon

    project = tmp_path / "proj"
    project.mkdir()
    commands = []

    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return TLDRDaemon(project), project, commands


def test_diagnostics_file_cannot_become_an_option(daemon):
    d, project, commands = daemon
    (project / "--fix").write_text("")
    assert d._handle_diagnostics({"file": "--fix"})["status"] == "ok"
    expected = str((project / "--fix").resolve())
    assert [cmd[-1] for cmd in commands] == [expected, expected]


def test_diagnostics_rejects_paths_outside_project(daemon):
    d, project, commands = daemon
    for path in ("../outside.py", "/etc/passwd"):
        assert d._handle_diagnostics({"file": path})["status"] == "error"
    assert commands == []


def test_semantic_index_cannot_choose_model(tmp_path, monkeypatch):
    import faiss

    from tldr.semantic import semantic_search

    cache = tmp_path / ".tldr" / "cache" / "semantic"
    cache.mkdir(parents=True)
    faiss.write_index(faiss.IndexFlatIP(4), str(cache / "index.faiss"))
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    (cache / "metadata.json").write_text(json.dumps({"units": [], "model": "attacker/model"}))
    with pytest.raises(ValueError, match="unsupported model"):
        semantic_search(str(tmp_path), "query")


def test_repo_directory_cannot_stand_in_for_model(tmp_path, monkeypatch):
    from tldr.semantic import DEFAULT_MODEL, SUPPORTED_MODELS, get_model

    (tmp_path / SUPPORTED_MODELS[DEFAULT_MODEL]["hf_name"]).mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="shadows the model"):
        get_model()
