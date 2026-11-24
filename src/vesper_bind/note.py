"""Append one STM note to an existing workspace. Never open a key file."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import math
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vesper_bind.errors import BindError
from vesper_bind.paths import (
    abspath,
    assert_symlinks_stay,
    atomic_replace,
    inside,
    read_regular,
    refuse_forbidden,
)

NOTE_TEXT = "vesper-bind wrote a receipt."
STM_CAP = 100
# vesper-runtime holds an exclusive flock on this file while it rewrites
# state.json (fork, remember, link, sleep). See its docs/memory.md,
# "Writers outside this program". The name is the shared contract.
LOCK_FILENAME = ".lock"


@dataclass(frozen=True)
class PreparedNote:
    """A note ready to commit, tied to the state.json it was built from."""

    note_id: str
    data: bytes
    base_sha256: str


def prepare_note(workspace: Path, now: int) -> PreparedNote:
    """Build the new state.json bytes. Do not write."""
    if isinstance(now, bool) or not isinstance(now, int):
        raise BindError("workspace state cannot take a note")
    root = _workspace_dir(workspace)
    state_path = root / "state.json"
    refuse_forbidden(state_path)
    if state_path.is_symlink() or not state_path.is_file():
        raise BindError("workspace state cannot take a note")
    if not inside(root, state_path):
        raise BindError("symlink resolves outside the directory")
    record = read_regular(state_path)
    document = _object(record.data)
    memory = document.get("memory")
    if not isinstance(memory, dict):
        raise BindError("workspace state cannot take a note")
    stm = memory.get("stm")
    if not isinstance(stm, list):
        raise BindError("workspace state cannot take a note")
    note_id = _note_id(now, len(stm))
    if note_id in _ids(memory):
        raise BindError("workspace state cannot take a note")
    item = {
        "id": note_id,
        "ts": now,
        "text": NOTE_TEXT,
        "valence": 0.5,
        "weight": 1.0,
        "tier": "stm",
        "pinned": False,
    }
    stm.append(item)
    while len(stm) > STM_CAP:
        index = min(range(len(stm)), key=lambda i: _order(stm[i]))
        del stm[index]
    if not any(isinstance(entry, dict) and entry.get("id") == note_id for entry in stm):
        raise BindError("workspace state cannot take a note")
    try:
        payload = json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    except (TypeError, ValueError) as exc:
        raise BindError("workspace state cannot take a note") from exc
    return PreparedNote(note_id, payload.encode("utf-8"), record.sha256)


def commit_note(workspace: Path, note: PreparedNote) -> None:
    """Replace state.json if it is still the file the note was built from.

    Holds the workspace lock so vesper-runtime cannot rewrite state.json
    between the check and the replace. If anything changed it since
    prepare_note, refuse instead of overwriting that change. On a failed
    replace, put the previous bytes back.
    """
    root = _workspace_dir(workspace)
    state_path = root / "state.json"
    with _workspace_lock(root):
        current = read_regular(state_path)
        if current.sha256 != note.base_sha256:
            raise BindError("workspace state changed during bind")
        try:
            atomic_replace(root, "state.json", note.data)
        except BindError:
            try:
                atomic_replace(root, "state.json", current.data)
            except BindError:
                pass
            raise


@contextlib.contextmanager
def _workspace_lock(root: Path) -> Iterator[None]:
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        fd = os.open(root / LOCK_FILENAME, flags, 0o600)
    except OSError as exc:
        raise BindError("workspace state cannot take a note") from exc
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _workspace_dir(workspace: Path) -> Path:
    root = abspath(workspace)
    refuse_forbidden(root)
    assert_symlinks_stay(root)
    if not root.exists():
        raise BindError("workspace is missing")
    if root.is_symlink():
        raise BindError("symlink resolves outside the directory")
    if not root.is_dir():
        raise BindError("workspace is missing")
    return root


def _note_id(now: int, existing: int) -> str:
    material = f"stm|{now}|{NOTE_TEXT}|{existing}".encode("utf-8")
    return "m-" + hashlib.sha256(material).hexdigest()[:16]


def _object(data: bytes) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BindError("workspace state cannot take a note") from exc
    try:
        document = json.loads(text, object_pairs_hook=_pairs, parse_constant=_reject_number)
    except BindError:
        raise
    except json.JSONDecodeError as exc:
        raise BindError("workspace state cannot take a note") from exc
    if not isinstance(document, dict):
        raise BindError("workspace state cannot take a note")
    return document


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise BindError("workspace state cannot take a note")
        document[key] = value
    return document


def _reject_number(name: str) -> None:
    raise BindError("workspace state cannot take a note")


def _ids(memory: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    for tier in ("stm", "semantic", "ltm", "graph"):
        items = memory.get(tier, [])
        if items is None:
            continue
        if not isinstance(items, list):
            raise BindError("workspace state cannot take a note")
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                found.add(item["id"])
    return found


def _order(item: Any) -> tuple[int, str]:
    if not isinstance(item, dict):
        raise BindError("workspace state cannot take a note")
    ts = item.get("ts")
    item_id = item.get("id")
    if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not isinstance(item_id, str):
        raise BindError("workspace state cannot take a note")
    if isinstance(ts, float) and not math.isfinite(ts):
        raise BindError("workspace state cannot take a note")
    return (ts, item_id)
