"""The receipt module loads, validates, and renders without the CLI."""

from __future__ import annotations

import json

import pytest

from vesper_bind.errors import BindError
from vesper_bind.receipt import SCHEMA_ID, SHOW_FIELDS, build_receipt, load_text


def _sample() -> str:
    flags = {
        "hypothesis_present": True,
        "hypothesis_not_dry_run": True,
        "hypothesis_not_mock": True,
        "scaffold_score_present": True,
        "scaffold_not_dry_run": True,
        "critic_not_reject": True,
    }
    digest = "a" * 64
    receipt = build_receipt(
        created_utc="2026-10-02T12:00:00Z",
        hypothesis_path="/tmp/hypothesis.json",
        hypothesis_size=12,
        hypothesis_mtime_utc="2026-10-02T11:00:00Z",
        hypothesis_sha256=digest,
        scaffold_path="/tmp/run",
        plan_md_sha256=digest,
        evidence_md_sha256=digest,
        critic_md_sha256=digest,
        score_json_sha256=digest,
        pass_flags=flags,
        vesper_note_id=None,
    )
    return receipt.to_json()


def test_reader_loads_json_without_the_checker() -> None:
    text = _sample()
    document = json.loads(text)
    assert document["schema"] == "vesper-bind/receipt/v1"
    assert text.endswith("\n")


def test_load_render_round_trip() -> None:
    receipt = load_text(_sample())
    assert receipt.schema == SCHEMA_ID
    lines = receipt.render().splitlines()
    assert [line.split(":", 1)[0] for line in lines] == list(SHOW_FIELDS)
    assert lines[-1] == "vesper_note_id: null"
    again = load_text(receipt.to_json())
    assert again.render() == receipt.render()


def test_extra_field_is_rejected() -> None:
    document = json.loads(_sample())
    document["prompt"] = "do not store this"
    with pytest.raises(BindError):
        load_text(json.dumps(document))


def test_false_flag_is_rejected() -> None:
    document = json.loads(_sample())
    document["pass_flags"]["hypothesis_not_mock"] = False
    with pytest.raises(BindError):
        load_text(json.dumps(document))
