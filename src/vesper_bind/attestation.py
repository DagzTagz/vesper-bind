"""Check the HMAC attestation Dagz-Scaffold's scorer adds to score-result.json.

Dagz-Scaffold `score.py --attest-key KEY` writes an `attestation` object:
schema `dagz-scaffold/score-attestation/v1`, alg `hmac-sha256`, `kid` (first 16
hex characters of SHA-256 of the key), `inputs` (SHA-256 of plan.md,
evidence.md, critic.md and score.json), and `mac`, which is HMAC-SHA256 over
canonical JSON of {"attestation": <the fields above>, "result": <every other
top-level field>}. Canonical JSON is sort_keys=True, separators=(",", ":"),
ensure_ascii=False, allow_nan=False: the same rule vesper-runtime uses.

Trust assumption: the key is a shared secret between the account that scores
and the account that binds. Anyone who can read it can attest anything. It
stops a hand-written or edited score-result.json only when the agent that
wrote the run folder cannot read the key.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import stat
from pathlib import Path
from typing import Any

from vesper_bind.errors import BindError
from vesper_bind.paths import abspath, inside, refuse_forbidden

SCHEMA = "dagz-scaffold/score-attestation/v1"
ALG = "hmac-sha256"
FIELD = "attestation"
INPUT_FILES = ("plan.md", "evidence.md", "critic.md", "score.json")
KEY_ENV = "DAGZ_SCORER_KEY_FILE"
_KEY_MAX = 4096
_HEADER = ("schema", "alg", "kid", "inputs")
_OPEN = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC


def canonical_bytes(obj: object) -> bytes:
    try:
        text = json.dumps(
            obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise BindError("scaffold scorer result is not canonical JSON") from exc
    return text.encode("utf-8")


def key_id(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()[:16]


def compute_mac(key: bytes, result: dict[str, Any], header: dict[str, Any]) -> str:
    body = canonical_bytes({"attestation": header, "result": result})
    return hmac.new(key, body, hashlib.sha256).hexdigest()


def key_path_from(flag: str | None) -> Path:
    raw = flag if flag else os.environ.get(KEY_ENV)
    if not raw:
        raise BindError(
            f"a scorer key is required: pass --scorer-key or set {KEY_ENV} "
            "(the key Dagz-Scaffold score.py --attest-key used)"
        )
    return Path(raw).expanduser()


def read_scorer_key(path: Path, *, not_inside: tuple[Path, ...] = ()) -> bytes:
    """Read the scorer key: a regular file you own, mode 0600 or 0400, hex text."""
    absolute = abspath(path)
    refuse_forbidden(absolute)
    for directory in not_inside:
        if inside(directory, absolute):
            raise BindError("scorer key must not be inside the scaffold run directory")
    if absolute.is_symlink():
        raise BindError("scorer key must not be a symbolic link")
    try:
        fd = os.open(absolute, _OPEN)
    except OSError as exc:
        raise BindError("scorer key is unreadable") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > _KEY_MAX:
            raise BindError("scorer key is unreadable")
        if info.st_uid != os.geteuid():
            raise BindError("scorer key is not owned by this user")
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise BindError("scorer key must be mode 0600 or 0400")
        data = os.read(fd, _KEY_MAX)
    finally:
        os.close(fd)
    try:
        key = bytes.fromhex(data.decode("ascii").strip())
    except (UnicodeDecodeError, ValueError) as exc:
        raise BindError("scorer key is not hex text") from exc
    if len(key) < 32:
        raise BindError("scorer key is shorter than 32 bytes")
    return key


def verify_attestation(document: dict[str, Any], digests: dict[str, str], key: bytes) -> None:
    """Raise BindError unless document is the scorer's attested output for these files."""
    att = document.get(FIELD)
    if not isinstance(att, dict):
        raise BindError(
            "scaffold scorer result is not attested. Score again with Dagz-Scaffold "
            "`python3 harness/score.py --attest-key KEY RUN_DIR > RUN_DIR/score-result.json`"
        )
    if set(att) != {*_HEADER, "mac"}:
        raise BindError("scaffold scorer attestation is malformed")
    if att["schema"] != SCHEMA or att["alg"] != ALG:
        raise BindError("scaffold scorer attestation schema is not supported")
    kid = att["kid"]
    if not isinstance(kid, str) or not hmac.compare_digest(kid, key_id(key)):
        raise BindError("scaffold scorer result was attested with a different scorer key")
    result = {k: v for k, v in document.items() if k != FIELD}
    header = {k: att[k] for k in _HEADER}
    mac = att["mac"]
    if not isinstance(mac, str) or not hmac.compare_digest(mac, compute_mac(key, result, header)):
        raise BindError("scaffold scorer attestation does not match (edited or forged)")
    inputs = att["inputs"]
    if not isinstance(inputs, dict) or set(inputs) != set(INPUT_FILES):
        raise BindError("scaffold scorer attestation is malformed")
    for name in INPUT_FILES:
        if not isinstance(inputs[name], str) or not hmac.compare_digest(inputs[name], digests[name]):
            raise BindError(f"scaffold {name} changed after it was scored")
