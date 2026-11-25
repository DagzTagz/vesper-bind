"""A scaffold run binds only when Dagz-Scaffold's scorer passed it (audit F2, F13)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from conftest import reattest

from vesper_bind import attestation
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


def test_passing_fixture_is_passed(scorer_key: bytes) -> None:
    bound = load_inputs(PASSING_H, PASSING_S, scorer_key=scorer_key)
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
def test_scorer_failure_is_refused(
    tmp_path: Path, capsys, changes: dict, scorer_key: bytes
) -> None:
    # A genuine (attested) scorer result that records a failure.
    scaffold = _copy_run(tmp_path)
    _edit_json(scaffold / SCORER_RESULT, **changes)
    reattest(scaffold, scorer_key)
    code, err = _bind(tmp_path, scaffold, capsys)
    assert code == 1
    assert "scorer did not pass" in err


def test_scorer_result_must_match_score_json(
    tmp_path: Path, capsys, scorer_key: bytes
) -> None:
    scaffold = _copy_run(tmp_path)
    result = json.loads((scaffold / SCORER_RESULT).read_text(encoding="utf-8"))
    result["score"]["verdict"] = "ACCEPT WITH WAIVERS"
    (scaffold / SCORER_RESULT).write_text(json.dumps(result) + "\n", encoding="utf-8")
    reattest(scaffold, scorer_key)
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


# Residual item S7: score-result.json must come from the scorer, not a text editor.

# Shared with Dagz-Scaffold harness/attest_selftest.py: both sides must agree.
VECTOR_KEY = bytes(range(32))
VECTOR_RESULT = {
    "ok": True,
    "fail_reasons": [],
    "summary": "ACCEPT",
    "score": {"rigor": 0.85, "verdict": "ACCEPT", "note": "caf\u00e9"},
}


def test_mac_matches_the_scaffold_vector() -> None:
    header = {
        "schema": attestation.SCHEMA,
        "alg": attestation.ALG,
        "kid": attestation.key_id(VECTOR_KEY),
        "inputs": {name: "0" * 64 for name in attestation.INPUT_FILES},
    }
    assert header["kid"] == "630dcd2966c43366"
    assert attestation.compute_mac(VECTOR_KEY, VECTOR_RESULT, header) == (
        "efee91859d66fb5bf0858b9cac0522c38cbd05b0067e00f39fcfe50811940e40"
    )


def test_hand_written_result_is_refused(tmp_path: Path, capsys) -> None:
    # The f2_repro.py forgery: evidence replaced by one line, and a matching
    # score-result.json typed by hand. Before this change it was bound.
    scaffold = _copy_run(tmp_path)
    (scaffold / "evidence.md").write_text("I did nothing. Trust me.\n", encoding="utf-8")
    score = json.loads((scaffold / "score.json").read_text(encoding="utf-8"))
    forged = {"ok": True, "fail_reasons": [], "score": score, "critic_verdict": "ACCEPT"}
    (scaffold / SCORER_RESULT).write_text(json.dumps(forged) + "\n", encoding="utf-8")
    code, err = _bind(tmp_path, scaffold, capsys)
    assert code == 1
    assert "not attested" in err


def test_edited_result_is_refused(tmp_path: Path, capsys) -> None:
    scaffold = _copy_run(tmp_path)
    _edit_json(scaffold / SCORER_RESULT, summary="ACCEPT, trust me")
    code, err = _bind(tmp_path, scaffold, capsys)
    assert code == 1
    assert "edited or forged" in err


def test_swapped_evidence_after_scoring_is_refused(tmp_path: Path, capsys) -> None:
    scaffold = _copy_run(tmp_path)
    (scaffold / "evidence.md").write_text("I did nothing. Trust me.\n", encoding="utf-8")
    code, err = _bind(tmp_path, scaffold, capsys)
    assert code == 1
    assert "evidence.md changed after it was scored" in err


def test_result_attested_with_another_key_is_refused(tmp_path: Path, capsys) -> None:
    scaffold = _copy_run(tmp_path)
    reattest(scaffold, b"\x01" * 32)
    code, err = _bind(tmp_path, scaffold, capsys)
    assert code == 1
    assert "different scorer key" in err


def test_unattested_state(tmp_path: Path, scorer_key: bytes) -> None:
    scaffold = _copy_run(tmp_path)
    _edit_json(scaffold / SCORER_RESULT, attestation=_DROP)
    from vesper_bind.errors import BindError

    with pytest.raises(BindError, match="not attested"):
        load_inputs(PASSING_H, scaffold, scorer_key=scorer_key)


def test_missing_key_is_refused(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.delenv(attestation.KEY_ENV)
    code, err = _bind(tmp_path, _copy_run(tmp_path), capsys)
    assert code == 1
    assert "scorer key is required" in err


def test_key_flag_overrides_env(tmp_path: Path, capsys, monkeypatch, scorer_key_file: Path) -> None:
    monkeypatch.setenv(attestation.KEY_ENV, str(tmp_path / "nope.key"))
    out = tmp_path / "receipts"
    code = run(
        [
            "bind",
            "--hypothesis",
            str(PASSING_H),
            "--scaffold-run",
            str(_copy_run(tmp_path)),
            "--out",
            str(out),
            "--scorer-key",
            str(scorer_key_file),
        ]
    )
    assert code == 0, capsys.readouterr().err


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o604])
def test_loose_key_is_refused(tmp_path: Path, capsys, scorer_key_file: Path, mode: int) -> None:
    scorer_key_file.chmod(mode)
    code, err = _bind(tmp_path, _copy_run(tmp_path), capsys)
    assert code == 1
    assert "mode 0600 or 0400" in err


def test_key_inside_run_folder_is_refused(
    tmp_path: Path, capsys, monkeypatch, scorer_key_file: Path
) -> None:
    scaffold = _copy_run(tmp_path)
    planted = scaffold / "scorer.key"
    shutil.copyfile(scorer_key_file, planted)
    planted.chmod(0o600)
    monkeypatch.setenv(attestation.KEY_ENV, str(planted))
    code, err = _bind(tmp_path, scaffold, capsys)
    assert code == 1
    assert "inside the scaffold run directory" in err


def test_symlinked_key_is_refused(tmp_path: Path, capsys, monkeypatch, scorer_key_file: Path) -> None:
    link = tmp_path / "link.key"
    link.symlink_to(scorer_key_file)
    monkeypatch.setenv(attestation.KEY_ENV, str(link))
    code, err = _bind(tmp_path, _copy_run(tmp_path), capsys)
    assert code == 1
    assert "symbolic link" in err
