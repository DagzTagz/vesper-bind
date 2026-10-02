"""Load, validate, and render a vesper-bind/receipt/v1 file.

A later reader can parse the JSON with the standard library. This module is
the checker the CLI uses. It does not import a GUI toolkit.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from vesper_bind import __version__
from vesper_bind.errors import BindError

SCHEMA_ID = "vesper-bind/receipt/v1"
PASS_FLAG_KEYS = (
    "hypothesis_present",
    "hypothesis_not_dry_run",
    "hypothesis_not_mock",
    "scaffold_score_present",
    "scaffold_not_dry_run",
    "critic_not_reject",
)
SHOW_FIELDS = (
    "schema",
    "created_utc",
    "tool_version",
    "hypothesis.path",
    "hypothesis.size",
    "hypothesis.mtime_utc",
    "hypothesis.sha256",
    "scaffold.path",
    "scaffold.plan_md.sha256",
    "scaffold.evidence_md.sha256",
    "scaffold.critic_md.sha256",
    "scaffold.score_json.sha256",
    "pass_flags.hypothesis_present",
    "pass_flags.hypothesis_not_dry_run",
    "pass_flags.hypothesis_not_mock",
    "pass_flags.scaffold_score_present",
    "pass_flags.scaffold_not_dry_run",
    "pass_flags.critic_not_reject",
    "vesper_note_id",
)

_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_NOTE_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_TOP_KEYS = (
    "schema",
    "created_utc",
    "tool_version",
    "hypothesis",
    "scaffold",
    "pass_flags",
    "vesper_note_id",
)
_HYPOTHESIS_KEYS = ("path", "size", "mtime_utc", "sha256")
_SCAFFOLD_KEYS = (
    "path",
    "plan_md_sha256",
    "evidence_md_sha256",
    "critic_md_sha256",
    "score_json_sha256",
)


@dataclass(frozen=True)
class Receipt:
    schema: str
    created_utc: str
    tool_version: str
    hypothesis_path: str
    hypothesis_size: int
    hypothesis_mtime_utc: str
    hypothesis_sha256: str
    scaffold_path: str
    plan_md_sha256: str
    evidence_md_sha256: str
    critic_md_sha256: str
    score_json_sha256: str
    pass_flags: dict[str, bool]
    vesper_note_id: str | None

    def to_obj(self) -> dict[str, Any]:
        flags = {key: self.pass_flags[key] for key in PASS_FLAG_KEYS}
        return {
            "schema": self.schema,
            "created_utc": self.created_utc,
            "tool_version": self.tool_version,
            "hypothesis": {
                "path": self.hypothesis_path,
                "size": self.hypothesis_size,
                "mtime_utc": self.hypothesis_mtime_utc,
                "sha256": self.hypothesis_sha256,
            },
            "scaffold": {
                "path": self.scaffold_path,
                "plan_md_sha256": self.plan_md_sha256,
                "evidence_md_sha256": self.evidence_md_sha256,
                "critic_md_sha256": self.critic_md_sha256,
                "score_json_sha256": self.score_json_sha256,
            },
            "pass_flags": flags,
            "vesper_note_id": self.vesper_note_id,
        }

    def to_json(self) -> str:
        text = json.dumps(self.to_obj(), indent=2, ensure_ascii=False, allow_nan=False)
        return text + "\n"

    def render(self) -> str:
        values = _show_values(self)
        lines = [f"{label}: {values[label]}" for label in SHOW_FIELDS]
        return "\n".join(lines) + "\n"


def build_receipt(
    *,
    created_utc: str,
    hypothesis_path: str,
    hypothesis_size: int,
    hypothesis_mtime_utc: str,
    hypothesis_sha256: str,
    scaffold_path: str,
    plan_md_sha256: str,
    evidence_md_sha256: str,
    critic_md_sha256: str,
    score_json_sha256: str,
    pass_flags: dict[str, bool],
    vesper_note_id: str | None,
) -> Receipt:
    receipt = Receipt(
        schema=SCHEMA_ID,
        created_utc=created_utc,
        tool_version=__version__,
        hypothesis_path=hypothesis_path,
        hypothesis_size=hypothesis_size,
        hypothesis_mtime_utc=hypothesis_mtime_utc,
        hypothesis_sha256=hypothesis_sha256,
        scaffold_path=scaffold_path,
        plan_md_sha256=plan_md_sha256,
        evidence_md_sha256=evidence_md_sha256,
        critic_md_sha256=critic_md_sha256,
        score_json_sha256=score_json_sha256,
        pass_flags={key: pass_flags[key] for key in PASS_FLAG_KEYS},
        vesper_note_id=vesper_note_id,
    )
    # Round-trip through the reader so a written file cannot drift from the schema.
    return load_text(receipt.to_json())


def load_text(text: str) -> Receipt:
    try:
        document = json.loads(text, object_pairs_hook=_pairs, parse_constant=_reject_number)
    except BindError:
        raise
    except json.JSONDecodeError as exc:
        raise BindError("receipt is unreadable") from exc
    return load_obj(document)


def load_obj(document: Any) -> Receipt:
    if not isinstance(document, dict):
        raise BindError("receipt is unreadable")
    _exact_keys(document, _TOP_KEYS, "receipt")
    if document["schema"] != SCHEMA_ID:
        raise BindError("receipt schema is not vesper-bind/receipt/v1")
    created = _utc(document["created_utc"], "created_utc")
    version = _plain(document["tool_version"], "tool_version")
    hypothesis = document["hypothesis"]
    scaffold = document["scaffold"]
    flags = document["pass_flags"]
    if not isinstance(hypothesis, dict) or not isinstance(scaffold, dict) or not isinstance(flags, dict):
        raise BindError("receipt is unreadable")
    _exact_keys(hypothesis, _HYPOTHESIS_KEYS, "hypothesis")
    _exact_keys(scaffold, _SCAFFOLD_KEYS, "scaffold")
    _exact_keys(flags, PASS_FLAG_KEYS, "pass_flags")
    checked_flags: dict[str, bool] = {}
    for key in PASS_FLAG_KEYS:
        if flags[key] is not True:
            raise BindError("receipt pass flag is not true")
        checked_flags[key] = True
    note = document["vesper_note_id"]
    if note is not None and (not isinstance(note, str) or _NOTE_RE.fullmatch(note) is None):
        raise BindError("receipt note id is invalid")
    return Receipt(
        schema=SCHEMA_ID,
        created_utc=created,
        tool_version=version,
        hypothesis_path=_abs_path(hypothesis["path"], "hypothesis.path"),
        hypothesis_size=_size(hypothesis["size"]),
        hypothesis_mtime_utc=_utc(hypothesis["mtime_utc"], "hypothesis.mtime_utc"),
        hypothesis_sha256=_sha(hypothesis["sha256"], "hypothesis.sha256"),
        scaffold_path=_abs_path(scaffold["path"], "scaffold.path"),
        plan_md_sha256=_sha(scaffold["plan_md_sha256"], "scaffold.plan_md_sha256"),
        evidence_md_sha256=_sha(scaffold["evidence_md_sha256"], "scaffold.evidence_md_sha256"),
        critic_md_sha256=_sha(scaffold["critic_md_sha256"], "scaffold.critic_md_sha256"),
        score_json_sha256=_sha(scaffold["score_json_sha256"], "scaffold.score_json_sha256"),
        pass_flags=checked_flags,
        vesper_note_id=note,
    )


def _show_values(receipt: Receipt) -> dict[str, str]:
    note = "null" if receipt.vesper_note_id is None else receipt.vesper_note_id
    values = {
        "schema": receipt.schema,
        "created_utc": receipt.created_utc,
        "tool_version": receipt.tool_version,
        "hypothesis.path": receipt.hypothesis_path,
        "hypothesis.size": str(receipt.hypothesis_size),
        "hypothesis.mtime_utc": receipt.hypothesis_mtime_utc,
        "hypothesis.sha256": receipt.hypothesis_sha256,
        "scaffold.path": receipt.scaffold_path,
        "scaffold.plan_md.sha256": receipt.plan_md_sha256,
        "scaffold.evidence_md.sha256": receipt.evidence_md_sha256,
        "scaffold.critic_md.sha256": receipt.critic_md_sha256,
        "scaffold.score_json.sha256": receipt.score_json_sha256,
        "vesper_note_id": note,
    }
    for key, flag in receipt.pass_flags.items():
        values[f"pass_flags.{key}"] = "true" if flag else "false"
    return values


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise BindError("receipt has a duplicate key")
        document[key] = value
    return document


def _reject_number(name: str) -> None:
    raise BindError(f"receipt has a non-finite number {name}")


def _exact_keys(document: dict[str, Any], expected: tuple[str, ...], what: str) -> None:
    found = tuple(document.keys())
    if found != expected:
        raise BindError(f"receipt {what} fields are not the schema")


def _utc(value: Any, what: str) -> str:
    if not isinstance(value, str) or _UTC_RE.fullmatch(value) is None:
        raise BindError(f"receipt {what} is invalid")
    return value


def _plain(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value or any(ch in value for ch in "\n\r\x00"):
        raise BindError(f"receipt {what} is invalid")
    if len(value) > 64:
        raise BindError(f"receipt {what} is invalid")
    return value


def _abs_path(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value.startswith("/") or len(value) > 4096:
        raise BindError(f"receipt {what} is invalid")
    if any(ch in value for ch in "\n\r\x00"):
        raise BindError(f"receipt {what} is invalid")
    return value


def _size(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BindError("receipt hypothesis.size is invalid")
    return value


def _sha(value: Any, what: str) -> str:
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise BindError(f"receipt {what} is invalid")
    return value
