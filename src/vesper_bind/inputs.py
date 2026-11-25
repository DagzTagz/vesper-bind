"""Read a hypothesis file and a scaffold run. Do not keep their prose."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from vesper_bind.attestation import verify_attestation
from vesper_bind.errors import BindError
from vesper_bind.paths import FileRecord, read_jailed_file, read_user_file, realpath
from vesper_bind.receipt import PASS_FLAG_KEYS

_SCAFFOLD_FILES = ("plan.md", "evidence.md", "critic.md", "score.json")
# stdout of Dagz-Scaffold `python3 harness/score.py RUN_DIR`, saved in RUN_DIR.
SCORER_RESULT = "score-result.json"
_SAFE_REASON = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_ .:-]{0,63}$")
_VERDICTS = ("REJECT", "ACCEPT WITH WAIVERS", "ACCEPT")
_VERDICT_HEADING = re.compile(r"^##[ \t]+VERDICT[ \t]*$", re.M)
_NEXT_HEADING = re.compile(r"^##[ \t]+", re.M)


class ScaffoldRunState(StrEnum):
    """Terminal state of a Dagz-Scaffold run, checked in this order.

    Only PASSED binds. score.json alone is the agent's claim: Scaffold's own
    failing examples all say quit_early=false and missing_evidence=false, and
    only the scorer finds the failure. So a run with no scorer result is
    UNSCORED, never PASSED. A score-result.json is plain JSON that anyone with
    write access to the run folder can type, so a result without a valid
    scorer attestation (HMAC with the scorer key) is UNATTESTED, never PASSED.
    """

    DRY_RUN = "dry_run"  # dry-run marker in score.json or evidence.md
    REJECTED = "rejected"  # critic verdict REJECT, or score.json disagrees
    FAILED = "failed"  # score.json or the scorer result records a failure
    UNSCORED = "unscored"  # no Dagz-Scaffold scorer result in the run folder
    UNATTESTED = "unattested"  # scorer result lacks a valid attestation for these files
    PASSED = "passed"  # attested scorer ok with no fail_reasons, for this score.json


@dataclass(frozen=True)
class ScaffoldOutcome:
    state: ScaffoldRunState
    reason: str = ""


@dataclass(frozen=True)
class BoundInputs:
    hypothesis: FileRecord
    scaffold_path: str
    plan_sha256: str
    evidence_sha256: str
    critic_sha256: str
    score_sha256: str
    pass_flags: dict[str, bool]
    scaffold_state: ScaffoldRunState


def load_inputs(hypothesis: Path, scaffold_run: Path, *, scorer_key: bytes) -> BoundInputs:
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
    outcome = scaffold_outcome(directory, score, files, scorer_key=scorer_key)

    flags = pass_flags(hypothesis_dry=dry, hypothesis_mock=mock, scaffold_state=outcome.state)
    if outcome.state is not ScaffoldRunState.PASSED:
        raise BindError(outcome.reason)
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
        scaffold_state=outcome.state,
    )


def pass_flags(
    *, hypothesis_dry: bool, hypothesis_mock: bool, scaffold_state: ScaffoldRunState
) -> dict[str, bool]:
    """Each flag is true only if its check ran and passed.

    The scaffold checks run in ScaffoldRunState order, so the critic verdict is
    not evaluated for a dry-run scaffold.
    """
    return {
        # Both files were read and parsed before this is called.
        "hypothesis_present": True,
        "hypothesis_not_dry_run": not hypothesis_dry,
        "hypothesis_not_mock": not hypothesis_mock,
        "scaffold_score_present": True,
        "scaffold_not_dry_run": scaffold_state is not ScaffoldRunState.DRY_RUN,
        "critic_not_reject": scaffold_state
        not in {ScaffoldRunState.DRY_RUN, ScaffoldRunState.REJECTED},
    }


def scaffold_outcome(
    directory: Path,
    score: dict[str, Any],
    files: dict[str, FileRecord],
    *,
    scorer_key: bytes,
) -> ScaffoldOutcome:
    """Classify a scaffold run. Fails closed: anything unproven is not PASSED."""
    if _scaffold_dry(score, files["evidence.md"].data):
        return ScaffoldOutcome(ScaffoldRunState.DRY_RUN, "scaffold run is dry-run")
    verdict = _critic_verdict(files["critic.md"].data)
    score_verdict = score.get("verdict")
    if score_verdict is not None:
        if not isinstance(score_verdict, str) or score_verdict not in _VERDICTS:
            raise BindError("scaffold critic verdict is missing")
        if score_verdict != verdict:
            if "REJECT" in {score_verdict, verdict}:
                return ScaffoldOutcome(
                    ScaffoldRunState.REJECTED, "scaffold critic verdict is REJECT"
                )
            raise BindError("scaffold critic verdict disagrees")
    if verdict == "REJECT":
        return ScaffoldOutcome(ScaffoldRunState.REJECTED, "scaffold critic verdict is REJECT")

    # Scaffold's score.py fails these whatever else the run shows. A missing or
    # non-boolean value is not a pass.
    if score.get("quit_early") is not False:
        return ScaffoldOutcome(ScaffoldRunState.FAILED, "scaffold run is quit-early")
    if score.get("missing_evidence") is not False:
        return ScaffoldOutcome(ScaffoldRunState.FAILED, "scaffold run is missing evidence")
    failed = _scorer_failure(score)
    if failed is not None:
        return ScaffoldOutcome(ScaffoldRunState.FAILED, failed)

    candidate = directory / SCORER_RESULT
    if not candidate.exists() and not candidate.is_symlink():
        return ScaffoldOutcome(
            ScaffoldRunState.UNSCORED,
            f"scaffold run has no scorer result ({SCORER_RESULT}). Save the output of "
            f"Dagz-Scaffold `python3 harness/score.py RUN_DIR` as RUN_DIR/{SCORER_RESULT}",
        )
    result = _json_object(
        read_jailed_file(directory, SCORER_RESULT).data,
        f"scaffold {SCORER_RESULT} is unreadable",
    )
    # Authenticity first: nothing in an unattested result is trusted. The
    # digests are of the bytes read above, the same bytes the receipt hashes.
    try:
        verify_attestation(result, {name: files[name].sha256 for name in files}, scorer_key)
    except BindError as exc:
        return ScaffoldOutcome(ScaffoldRunState.UNATTESTED, str(exc))
    failed = _scorer_failure(result, required=True)
    if failed is not None:
        return ScaffoldOutcome(ScaffoldRunState.FAILED, failed)
    if result.get("score") != score:
        return ScaffoldOutcome(
            ScaffoldRunState.FAILED, "scaffold scorer result does not match score.json"
        )
    critic_verdict = result.get("critic_verdict", verdict)
    if critic_verdict != verdict:
        return ScaffoldOutcome(
            ScaffoldRunState.FAILED, "scaffold scorer result does not match critic.md"
        )
    return ScaffoldOutcome(ScaffoldRunState.PASSED)


def _scorer_failure(document: dict[str, Any], *, required: bool = False) -> str | None:
    """Message if a Scaffold scorer document is not a pass, else None."""
    ok = document.get("ok", None if required else True)
    reasons = document.get("fail_reasons", None if required else [])
    if ok is True and isinstance(reasons, list) and not reasons:
        return None
    message = "scaffold scorer did not pass"
    if isinstance(reasons, list) and reasons:
        safe = [r for r in reasons if isinstance(r, str) and _SAFE_REASON.fullmatch(r)]
        if safe:
            message += f": {', '.join(safe[:8])}"
    return message


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
