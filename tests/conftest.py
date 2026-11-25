"""Shared test setup: a private copy of the public demo scorer key."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from vesper_bind import attestation

ROOT = Path(__file__).resolve().parents[1]
DEMO_KEY = ROOT / "examples" / "demo-scorer.key"


@pytest.fixture(autouse=True)
def scorer_key_file(tmp_path_factory, monkeypatch) -> Path:
    """Copy the demo key to a 0600 file outside any run folder and export it."""
    path = tmp_path_factory.mktemp("scorer-key") / "scorer.key"
    shutil.copyfile(DEMO_KEY, path)
    path.chmod(0o600)
    monkeypatch.setenv(attestation.KEY_ENV, str(path))
    return path


@pytest.fixture
def scorer_key(scorer_key_file: Path) -> bytes:
    return attestation.read_scorer_key(scorer_key_file)


def reattest(run_dir: Path, key: bytes) -> None:
    """Re-attest run_dir/score-result.json the way Dagz-Scaffold's scorer does."""
    path = run_dir / "score-result.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document.pop(attestation.FIELD, None)
    header = {
        "schema": attestation.SCHEMA,
        "alg": attestation.ALG,
        "kid": attestation.key_id(key),
        "inputs": {
            name: hashlib.sha256((run_dir / name).read_bytes()).hexdigest()
            for name in attestation.INPUT_FILES
        },
    }
    document[attestation.FIELD] = {**header, "mac": attestation.compute_mac(key, document, header)}
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
