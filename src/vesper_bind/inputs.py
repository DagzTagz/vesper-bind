"""Read a hypothesis file and a scaffold run. Do not keep their prose."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vesper_bind.errors import BindError
from vesper_bind.paths import FileRecord, read_jailed_file, read_user_file, realpath
from vesper_bind.receipt import PASS_FLAG_KEYS

_SCAFFOLD_FILES = ("plan.md", "evidence.md", "critic.md", "score.json")
_VERDICTS = ("REJECT", "ACCEPT WITH WAIVERS", "ACCEPT")
_VERDICT_HEADING = re.compile(r"^##[ \t]+VERDICT[ \t]*$", re.M)
_NEXT_HEADING = re.compile(r"^##[ \t]+", re.M)


@dataclass(frozen=True)
class BoundInputs:
    hypothesis: FileRecord
    scaffold_path: str
    plan_sha256: str
    evidence_sha256: str
    critic_sha256: str
    score_sha256: str
    pass_flags: dict[str, bool]


def load_inputs(hypothesis: Path, scaffold_run: Path) -> BoundInputs:
    hypothesis_record = read_user_file(
        hypothesis,
        missing="hypothesis file is missing",
        unreadable="hypothesis file is unreadable",
    )
    document = _json_object(hypothesis_record.data, "hypothesis file is unreadable")
    dry, mock = _hypothesis_markers(document)
    if dry:
        raise BindError("hypothesis file is marked dry-run")
    if mock:
        raise BindError("hypothesis file is marked mock")

    directory = Path(scaffold_run)
    files = {name: read_jailed_file(directory, name) for name in _SCAFFOLD_FILES}
    score = _json_object(files["score.json"].data, "scaffold score.json is unreadable")
    if _scaffold_dry(score, files["evidence.md"].data):
        raise BindError("scaffold run is dry-run")
    verdict = _critic_verdict(files["critic.md"].data)
    score_verdict = score.get("verdict")
    if score_verdict is not None:
        if not isinstance(score_verdict, str) or score_verdict not in _VERDICTS:
            raise BindError("scaffold critic verdict is missing")
        if score_verdict != verdict:
            if "REJECT" in {score_verdict, verdict}:
                raise BindError("scaffold critic verdict is REJECT")
            raise BindError("scaffold critic verdict disagrees")
    if verdict == "REJECT":
        raise BindError("scaffold critic verdict is REJECT")

    flags = {
        "hypothesis_present": True,
        "hypothesis_not_dry_run": True,
        "hypothesis_not_mock": True,
        "scaffold_score_present": True,
        "scaffold_not_dry_run": True,
        "critic_not_reject": True,
    }
    if tuple(flags) != PASS_FLAG_KEYS or not all(flags.values()):
        raise BindError("inputs did not pass")
    return BoundInputs(
        hypothesis=hypothesis_record,
        scaffold_path=str(realpath(directory)),
        plan_sha256=files["plan.md"].sha256,
        evidence_sha256=files["evidence.md"].sha256,
        critic_sha256=files["critic.md"].sha256,
        score_sha256=files["score.json"].sha256,
        pass_flags=flags,
    )


def _json_object(data: bytes, message: str) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BindError(message) from exc
    try:
        document = json.loads(text, object_pairs_hook=_pairs, parse_constant=_reject_number)
    except BindError:
        raise
    except json.JSONDecodeError as exc:
        raise BindError(message) from exc
    if not isinstance(document, dict):
        raise BindError(message)
    return document


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise BindError("file has a duplicate key")
        document[key] = value
    return document


def _reject_number(name: str) -> None:
    raise BindError("file has a non-finite number")


def _hypothesis_markers(document: dict[str, Any]) -> tuple[bool, bool]:
    dry = False
    mock = False

    def walk(node: Any) -> None:
        nonlocal dry, mock
        if isinstance(node, dict):
            for key, value in node.items():
                # JSON true is a dry-run mark. Any other present value is not
                # an explicit live flag. A missing key is not a mark: the
                # hypothesis engine omits meta.dry_run on a live run.
                if key == "dry_run" and value is not False:
                    dry = True
                if key in {"backend", "retrieval_backend"} and value == "mock":
                    mock = True
                if key == "domain" and value == "mock":
                    mock = True
                if (
                    key == "retrieval_status"
                    and isinstance(value, str)
                    and (value == "ok_mock" or value.endswith("_mock"))
                ):
                    mock = True
                if isinstance(value, str) and value.startswith("mock://"):
                    mock = True
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(document)
    return dry, mock


def _scaffold_dry(score: dict[str, Any], evidence: bytes) -> bool:
    if "dry_run" in score and score["dry_run"] is not False:
        return True
    notes = score.get("notes")
    if isinstance(notes, str) and notes.startswith("Synthetic dry-run"):
        return True
    try:
        text = evidence.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BindError("scaffold evidence.md is unreadable") from exc
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped.startswith("DRY-RUN MOCK")
    return False


def _critic_verdict(data: bytes) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BindError("scaffold critic.md is unreadable") from exc
    match = _VERDICT_HEADING.search(text)
    if match is None:
        raise BindError("scaffold critic verdict is missing")
    rest = text[match.end() :]
    next_heading = _NEXT_HEADING.search(rest)
    body = rest[: next_heading.start()] if next_heading is not None else rest
    for line in body.splitlines():
        candidate = line.strip().strip("*").strip("`")
        if candidate in _VERDICTS:
            return candidate
    raise BindError("scaffold critic verdict is missing")
