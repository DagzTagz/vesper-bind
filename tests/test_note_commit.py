"""commit_note is a compare-and-swap under the workspace lock (audit F11)."""

from __future__ import annotations

import fcntl
import json
import os
import stat
import threading
from pathlib import Path

import pytest

from vesper_bind import cli
from vesper_bind.cli import run
from vesper_bind.errors import BindError
from vesper_bind.note import LOCK_FILENAME, commit_note, prepare_note

ROOT = Path(__file__).resolve().parents[1]
PASSING_H = ROOT / "examples" / "passing" / "hypothesis.json"
PASSING_S = ROOT / "examples" / "passing" / "scaffold"


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    state = {
        "universe_id": "uni-fixture",
        "schema_version": "2",
        "memory": {"stm": [], "semantic": [], "graph": [], "ltm": []},
        "forks": [],
        "head": None,
    }
    state_path = workspace / "state.json"
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.chmod(state_path, 0o600)
    return workspace


def _remember_elsewhere(workspace: Path) -> bytes:
    """What `vesper remember` would do between prepare and commit."""
    state_path = workspace / "state.json"
    document = json.loads(state_path.read_text(encoding="utf-8"))
    document["memory"]["stm"].append({"id": "m-runtime", "ts": 1, "tier": "stm"})
    data = (json.dumps(document, indent=2) + "\n").encode("utf-8")
    state_path.write_bytes(data)
    return data


def test_commit_refuses_state_that_changed_after_prepare(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    note = prepare_note(workspace, 1_700_000_000)
    theirs = _remember_elsewhere(workspace)
    with pytest.raises(BindError, match="changed during bind"):
        commit_note(workspace, note)
    assert (workspace / "state.json").read_bytes() == theirs


def test_bind_leaves_no_receipt_when_state_changed(tmp_path: Path, monkeypatch, capsys) -> None:
    workspace = _workspace(tmp_path)
    real_prepare = cli.prepare_note

    def prepare_then_race(path: Path, now: int):
        note = real_prepare(path, now)
        _remember_elsewhere(path)
        return note

    monkeypatch.setattr(cli, "prepare_note", prepare_then_race)
    out = tmp_path / "receipts"
    code = run(
        [
            "bind",
            "--hypothesis",
            str(PASSING_H),
            "--scaffold-run",
            str(PASSING_S),
            "--out",
            str(out),
            "--vesper-workspace",
            str(workspace),
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "changed during bind" in captured.err
    assert not out.exists()
    saved = json.loads((workspace / "state.json").read_text(encoding="utf-8"))
    assert [item["id"] for item in saved["memory"]["stm"]] == ["m-runtime"]


def test_commit_waits_for_the_runtime_lock(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    note = prepare_note(workspace, 1_700_000_000)
    held = os.open(workspace / LOCK_FILENAME, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(held, fcntl.LOCK_EX)
    done = threading.Event()

    def commit() -> None:
        commit_note(workspace, note)
        done.set()

    worker = threading.Thread(target=commit)
    worker.start()
    try:
        assert not done.wait(0.3), "commit_note did not wait for the lock"
    finally:
        os.close(held)
    worker.join(5)
    assert done.is_set()
    saved = json.loads((workspace / "state.json").read_text(encoding="utf-8"))
    assert saved["memory"]["stm"][0]["id"] == note.note_id
    assert stat.S_IMODE((workspace / LOCK_FILENAME).stat().st_mode) == 0o600


def test_commit_refuses_a_symlinked_lock(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    note = prepare_note(workspace, 1_700_000_000)
    target = tmp_path / "elsewhere"
    (workspace / LOCK_FILENAME).symlink_to(target)
    with pytest.raises(BindError):
        commit_note(workspace, note)
    assert not target.exists()
