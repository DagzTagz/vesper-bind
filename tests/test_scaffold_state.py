"""A scaffold run binds only when Dagz-Scaffold's scorer passed it (audit F2, F13)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from vesper_bind.cli import run
from vesper_bind.inputs import (
    SCORER_RESULT,
    ScaffoldRunState,
    load_inputs,
    pass_flags,
)

ROOT = Path(__file__).resolve().parents[1]
PASSING_H = ROOT / "examples" / "passing" / "hypothesis.json"
PASSING_S = ROOT / "examples" / "passing" / "scaffold"


def _copy_run(tmp_path: Path) -> Path:
    scaffold = tmp_path / "run"
    shutil.copytree(PASSING_S, scaffold)
    return scaffold


def _edit_json(path: Path, **changes: object) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    for key, value in changes.items():
        if value is _DROP:
            document.pop(key, None)
        else:
            document[key] = value
    path.write_text(json.dumps(document) + "\n", encoding="utf-8")


_DROP = object()


def _bind(tmp_path: Path, scaffold: Path, capsys) -> tuple[int, str]:
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
    if code != 0:
        assert captured.out == ""
        assert not out.exists()
    return code, captured.err


def test_passing_fixture_is_passed() -> None:
    bound = load_inputs(PASSING_H, PASSING_S)
    assert bound.scaffold_state is ScaffoldRunState.PASSED
    assert all(bound.pass_flags.values())


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"quit_early": True}, "quit-early"),
        ({"missing_evidence": True}, "missing evidence"),
        ({"quit_early": True, "missing_evidence": True}, "quit-early"),
        ({"quit_early": _DROP}, "quit-early"),
        ({"missing_evidence": "false"}, "missing evidence"),
    ],
)
def test_score_json_failure_claims_are_refused(
    tmp_path: Path, capsys, changes: dict, message: str
) -> None:
    # The audit reproduction: score.json says the run quit early or lacks
    # evidence, which Scaffold's scorer fails, and bind used to accept it.
    scaffold = _copy_run(tmp_path)
    _edit_json(scaffold / "score.json", **changes)
    code, err = _bind(tmp_path, scaffold, capsys)
    assert code == 1
    assert message in err


def test_unscored_run_is_refused(tmp_path: Path, capsys) -> None:
    # Dagz-Scaffold's failing examples all claim quit_early=false and
    # missing_evidence=false in score.json. Only the scorer finds the failure,
    # so a run with no scorer result is not bindable.
    scaffold = _copy_run(tmp_path)
    (scaffold / SCORER_RESULT).unlink()
    code, err = _bind(tmp_path, scaffold, capsys)
    assert code == 1
    assert "no scorer result" in err


@pytest.mark.parametrize(
    "changes",
    [
        {"ok": False, "fail_reasons": ["required_verification"]},
        {"ok": False, "fail_reasons": ["quit_early"]},
        {"ok": True, "fail_reasons": ["solution_not_called"]},
        {"ok": "true"},
        {"ok": _DROP},
        {"fail_reasons": _DROP},
        {"fail_reasons": "none"},
    ],
)
def test_scorer_failure_is_refused(tmp_path: Path, capsys, changes: dict) -> None:
    scaffold = _copy_run(tmp_path)
    _edit_json(scaffold / SCORER_RESULT, **changes)
    code, err = _bind(tmp_path, scaffold, capsys)
    assert code == 1
    assert "scorer did not pass" in err


def test_scorer_result_must_match_score_json(tmp_path: Path, capsys) -> None:
    scaffold = _copy_run(tmp_path)
    result = json.loads((scaffold / SCORER_RESULT).read_text(encoding="utf-8"))
    result["score"]["verdict"] = "ACCEPT WITH WAIVERS"
    (scaffold / SCORER_RESULT).write_text(json.dumps(result) + "\n", encoding="utf-8")
    code, err = _bind(tmp_path, scaffold, capsys)
    assert code == 1
    assert "does not match score.json" in err


def test_unreadable_scorer_result_is_refused(tmp_path: Path, capsys) -> None:
    scaffold = _copy_run(tmp_path)
    (scaffold / SCORER_RESULT).write_text("[]\n", encoding="utf-8")
    code, err = _bind(tmp_path, scaffold, capsys)
    assert code == 1
    assert "unreadable" in err


def test_pass_flags_follow_the_checks() -> None:
    # F13: the flags are computed, so a failed check shows up as false.
    flags = pass_flags(
        hypothesis_dry=False,
        hypothesis_mock=True,
        scaffold_state=ScaffoldRunState.PASSED,
    )
    assert flags["hypothesis_not_mock"] is False
    assert flags["hypothesis_not_dry_run"] is True
    flags = pass_flags(
        hypothesis_dry=False,
        hypothesis_mock=False,
        scaffold_state=ScaffoldRunState.DRY_RUN,
    )
    assert flags["scaffold_not_dry_run"] is False
    flags = pass_flags(
        hypothesis_dry=False,
        hypothesis_mock=False,
        scaffold_state=ScaffoldRunState.REJECTED,
    )
    assert flags["critic_not_reject"] is False
    assert flags["scaffold_not_dry_run"] is True
