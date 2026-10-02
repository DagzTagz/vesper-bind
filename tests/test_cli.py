"""CLI behavior for dry-run, bind, verify, and show."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from vesper_bind.cli import run
from vesper_bind.note import NOTE_TEXT
from vesper_bind.receipt import SHOW_FIELDS

ROOT = Path(__file__).resolve().parents[1]
PASSING_H = ROOT / "examples" / "passing" / "hypothesis.json"
PASSING_S = ROOT / "examples" / "passing" / "scaffold"
FAIL_H = ROOT / "examples" / "fail-dry-run" / "hypothesis.json"
FAIL_S = ROOT / "examples" / "fail-dry-run" / "scaffold"
MARKER = "BINDER-FIXTURE-STATEMENT"


def test_dry_run_writes_nothing(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    code = run(
        ["--dry-run", "--hypothesis", str(PASSING_H), "--scaffold-run", str(PASSING_S)]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert list(tmp_path.iterdir()) == []
    document = json.loads(captured.out)
    assert document["schema"] == "vesper-bind/receipt/v1"
    assert document["vesper_note_id"] is None
    assert captured.out.endswith("\n")
    assert MARKER not in captured.out
    assert MARKER not in captured.err


def test_dry_run_scaffold_exits_1(capsys) -> None:
    code = run(
        ["--dry-run", "--hypothesis", str(PASSING_H), "--scaffold-run", str(FAIL_S)]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "dry-run" in captured.err


def test_reject_scaffold_exits_1(tmp_path: Path, capsys) -> None:
    scaffold = tmp_path / "run"
    shutil.copytree(PASSING_S, scaffold)
    critic = (scaffold / "critic.md").read_text(encoding="utf-8")
    critic = critic.replace("ACCEPT", "REJECT", 1)
    (scaffold / "critic.md").write_text(critic, encoding="utf-8")
    score = json.loads((scaffold / "score.json").read_text(encoding="utf-8"))
    score["verdict"] = "REJECT"
    (scaffold / "score.json").write_text(json.dumps(score) + "\n", encoding="utf-8")
    out = tmp_path / "receipts"
    code = run(
        [
            "bind",
            "--hypothesis",
            str(PASSING_H),
            "--scaffold-run",
            str(scaffold),
            "--out",
            str(out),
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "REJECT" in captured.err
    assert not out.exists()
    assert captured.out == ""


def test_dry_run_scaffold_bind_exits_1(tmp_path: Path, capsys) -> None:
    out = tmp_path / "receipts"
    code = run(
        [
            "bind",
            "--hypothesis",
            str(PASSING_H),
            "--scaffold-run",
            str(FAIL_S),
            "--out",
            str(out),
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "dry-run" in captured.err
    assert not out.exists()


def test_mock_hypothesis_exits_1(tmp_path: Path, capsys) -> None:
    hypothesis = tmp_path / "hypothesis.json"
    document = json.loads(PASSING_H.read_text(encoding="utf-8"))
    document["meta"]["retrieval_backend"] = "mock"
    hypothesis.write_text(json.dumps(document) + "\n", encoding="utf-8")
    out = tmp_path / "receipts"
    code = run(
        [
            "bind",
            "--hypothesis",
            str(hypothesis),
            "--scaffold-run",
            str(PASSING_S),
            "--out",
            str(out),
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "mock" in captured.err
    assert not out.exists()
    code = run(
        ["--dry-run", "--hypothesis", str(FAIL_H), "--scaffold-run", str(PASSING_S)]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "dry-run" in captured.err


def test_symlink_escape_exits_1(tmp_path: Path, capsys) -> None:
    scaffold = tmp_path / "run"
    shutil.copytree(PASSING_S, scaffold)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "plan.md").write_text("SECRET-BODY\n", encoding="utf-8")
    (scaffold / "plan.md").unlink()
    (scaffold / "plan.md").symlink_to(outside / "plan.md")
    out = tmp_path / "receipts"
    code = run(
        [
            "bind",
            "--hypothesis",
            str(PASSING_H),
            "--scaffold-run",
            str(scaffold),
            "--out",
            str(out),
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "symlink" in captured.err
    assert "SECRET-BODY" not in captured.err
    assert not out.exists()

    # The hypothesis parent is tmp_path, so the target must leave tmp_path.
    escaped_dir = tmp_path.parent / f"vesper-bind-escape-{tmp_path.name}"
    escaped_dir.mkdir()
    try:
        target = escaped_dir / "hypothesis.json"
        target.write_text("SECRET-BODY\n", encoding="utf-8")
        escaped = tmp_path / "escaped.json"
        escaped.symlink_to(target)
        code = run(
            [
                "bind",
                "--hypothesis",
                str(escaped),
                "--scaffold-run",
                str(PASSING_S),
                "--out",
                str(out),
            ]
        )
        captured = capsys.readouterr()
        assert code == 1
        assert "SECRET-BODY" not in captured.err
        assert not out.exists()
    finally:
        shutil.rmtree(escaped_dir)


def test_good_bind_is_mode_0600(tmp_path: Path, capsys) -> None:
    out = tmp_path / "receipts"
    old = os.umask(0)
    try:
        code = run(
            [
                "bind",
                "--hypothesis",
                str(PASSING_H),
                "--scaffold-run",
                str(PASSING_S),
                "--out",
                str(out),
            ]
        )
    finally:
        os.umask(old)
    captured = capsys.readouterr()
    assert code == 0
    path = Path(captured.out.strip())
    assert path.is_file()
    assert path.parent == out.resolve()
    info = path.lstat()
    assert stat.S_ISREG(info.st_mode)
    assert stat.S_IMODE(info.st_mode) == 0o600
    assert stat.S_IMODE(out.lstat().st_mode) == 0o700
    assert list(out.iterdir()) == [path]
    body = path.read_text(encoding="utf-8")
    assert body.endswith("\n")
    assert MARKER not in body
    document = json.loads(body)
    assert document["schema"] == "vesper-bind/receipt/v1"
    assert document["pass_flags"]["critic_not_reject"] is True


def test_verify_fails_after_one_flipped_byte(tmp_path: Path, capsys) -> None:
    hypothesis = tmp_path / "hypothesis.json"
    scaffold = tmp_path / "run"
    shutil.copyfile(PASSING_H, hypothesis)
    shutil.copytree(PASSING_S, scaffold)
    out = tmp_path / "receipts"
    code = run(
        [
            "bind",
            "--hypothesis",
            str(hypothesis),
            "--scaffold-run",
            str(scaffold),
            "--out",
            str(out),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    receipt = Path(captured.out.strip())
    original = hypothesis.read_bytes()
    flipped = bytearray(original)
    flipped[len(flipped) // 2] ^= 0x01
    hypothesis.write_bytes(flipped)
    code = run(["verify", str(receipt)])
    captured = capsys.readouterr()
    assert code == 1
    assert "digest mismatch" in captured.err
    hypothesis.write_bytes(original)
    os.chmod(receipt, 0o644)
    code = run(["verify", str(receipt)])
    captured = capsys.readouterr()
    assert code == 1
    assert "0600" in captured.err


def test_show_prints_schema_id(tmp_path: Path, capsys) -> None:
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
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    receipt = captured.out.strip()
    code = run(["show", receipt])
    shown = capsys.readouterr()
    assert code == 0
    assert "vesper-bind/receipt/v1" in shown.out
    labels = [line.split(":", 1)[0] for line in shown.out.splitlines()]
    assert labels == list(SHOW_FIELDS)
    document = json.loads(Path(receipt).read_text(encoding="utf-8"))
    assert document["schema"] == "vesper-bind/receipt/v1"
    assert "hypothesis" in document


def test_missing_workspace_writes_nothing(tmp_path: Path, capsys) -> None:
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
            str(tmp_path / "missing-workspace"),
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "workspace is missing" in captured.err
    assert not out.exists()
    assert captured.out == ""


def test_workspace_note_does_not_open_keys(tmp_path: Path, monkeypatch, capsys) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    identity = workspace / "identity"
    identity.mkdir(mode=0o700)
    hmac_key = identity / "hmac.key"
    private = identity / "edcsa-p256.priv"
    hmac_key.write_bytes(b"not-a-real-key\n")
    private.write_bytes(b"not-a-real-key\n")
    os.chmod(hmac_key, 0o600)
    os.chmod(private, 0o600)
    state = {
        "universe_id": "uni-fixture",
        "schema_version": "2",
        "character": {
            "id": "char-fixture",
            "callsign": "fixture",
            "straussian_level": 1,
        },
        "memory": {"stm": [], "semantic": [], "graph": [], "ltm": []},
        "forks": [],
        "head": None,
    }
    state_path = workspace / "state.json"
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.chmod(state_path, 0o600)
    before = {path: path.read_bytes() for path in (hmac_key, private)}

    real_open = os.open

    def guard(path, flags, *args, **kwargs):
        text = os.fsdecode(path)
        parts = Path(text).parts
        name = Path(text).name
        if "identity" in parts or name == "hmac.key" or name.endswith(".priv"):
            raise AssertionError(text)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", guard)
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
    assert code == 0, captured.err
    receipt_path = Path(captured.out.strip())
    document = json.loads(receipt_path.read_bytes().decode("utf-8"))
    note_id = document["vesper_note_id"]
    assert isinstance(note_id, str) and note_id.startswith("m-")
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    note = saved["memory"]["stm"][0]
    assert note["id"] == note_id
    assert note["text"] == NOTE_TEXT
    assert note["tier"] == "stm"
    assert MARKER not in state_path.read_text(encoding="utf-8")
    assert MARKER not in receipt_path.read_text(encoding="utf-8")
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
    monkeypatch.undo()
    for path, payload in before.items():
        assert path.read_bytes() == payload


def test_key_path_is_refused(tmp_path: Path, capsys) -> None:
    secret = tmp_path / "notes.priv"
    secret.write_text(MARKER + "\n", encoding="utf-8")
    code = run(
        [
            "bind",
            "--hypothesis",
            str(secret),
            "--scaffold-run",
            str(PASSING_S),
            "--out",
            str(tmp_path / "receipts"),
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "key file" in captured.err
    assert MARKER not in captured.err
    assert not (tmp_path / "receipts").exists()


def test_module_entry_dry_run(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "vesper_bind",
            "--dry-run",
            "--hypothesis",
            str(PASSING_H),
            "--scaffold-run",
            str(PASSING_S),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "vesper-bind/receipt/v1" in proc.stdout
    assert list(tmp_path.iterdir()) == []


def test_live_hypothesis_without_dry_run_key(tmp_path: Path, capsys) -> None:
    document = json.loads(PASSING_H.read_text(encoding="utf-8"))
    document["meta"].pop("dry_run", None)
    assert "dry_run" not in document["meta"]
    hypothesis = tmp_path / "hypothesis.json"
    hypothesis.write_text(json.dumps(document) + "\n", encoding="utf-8")
    out = tmp_path / "receipts"
    code = run(
        [
            "bind",
            "--hypothesis",
            str(hypothesis),
            "--scaffold-run",
            str(PASSING_S),
            "--out",
            str(out),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert "BINDER-FIXTURE-STATEMENT" not in Path(captured.out.strip()).read_text(encoding="utf-8")


def test_symlink_scaffold_root_exits_1(tmp_path: Path, capsys) -> None:
    real = tmp_path / "real"
    shutil.copytree(PASSING_S, real)
    link = tmp_path / "run"
    link.symlink_to(real)
    out = tmp_path / "receipts"
    code = run(
        [
            "bind",
            "--hypothesis",
            str(PASSING_H),
            "--scaffold-run",
            str(link),
            "--out",
            str(out),
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "symlink" in captured.err
    assert not out.exists()
    parent_link = tmp_path / "parent-link"
    parent_link.symlink_to(tmp_path)
    code = run(
        [
            "bind",
            "--hypothesis",
            str(PASSING_H),
            "--scaffold-run",
            str(parent_link),
            "--out",
            str(out),
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert not out.exists()


def test_harness_notes_mark_dry_run_without_key(tmp_path: Path, capsys) -> None:
    scaffold = tmp_path / "run"
    shutil.copytree(PASSING_S, scaffold)
    score = json.loads((scaffold / "score.json").read_text(encoding="utf-8"))
    score.pop("dry_run", None)
    score["notes"] = "Synthetic dry-run fixture. No secrets."
    (scaffold / "score.json").write_text(json.dumps(score) + "\n", encoding="utf-8")
    out = tmp_path / "receipts"
    code = run(
        [
            "bind",
            "--hypothesis",
            str(PASSING_H),
            "--scaffold-run",
            str(scaffold),
            "--out",
            str(out),
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "dry-run" in captured.err
    assert not out.exists()


def test_float_timestamp_at_stm_cap(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    items = [
        {
            "id": f"m-old-{index:03d}",
            "ts": float(index),
            "text": "old",
            "valence": 0.5,
            "weight": 1.0,
            "tier": "stm",
            "pinned": False,
        }
        for index in range(100)
    ]
    state = {
        "universe_id": "uni-fixture",
        "schema_version": "2",
        "character": {"id": "char-fixture", "callsign": "fixture", "straussian_level": 1},
        "memory": {"stm": items, "semantic": [], "graph": [], "ltm": []},
        "forks": [],
        "head": None,
    }
    state_path = workspace / "state.json"
    state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")
    os.chmod(state_path, 0o600)
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
    assert code == 0, captured.err
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert len(saved["memory"]["stm"]) == 100
    assert saved["memory"]["stm"][-1]["text"] == NOTE_TEXT


def test_docs_state_the_boundary() -> None:
    for name in ("README.md", "getting-started.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "does not call Grok" in text
        assert "does not train a model" in text
