"""Console script for vesper-bind. Local files only."""

from __future__ import annotations

import argparse
import os
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from vesper_bind import __version__
from vesper_bind.errors import BindError
from vesper_bind.inputs import load_inputs
from vesper_bind.note import commit_note, prepare_note
from vesper_bind.paths import (
    abspath,
    atomic_create,
    digest_if_present,
    ensure_private_dir,
    read_regular,
    refuse_forbidden,
)
from vesper_bind.receipt import Receipt, build_receipt, load_text

_SCAFFOLD_DIGESTS = (
    ("plan.md", "plan_md_sha256"),
    ("evidence.md", "evidence_md_sha256"),
    ("critic.md", "critic_md_sha256"),
    ("score.json", "score_json_sha256"),
)


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(f"vesper-bind: {message}", file=sys.stderr)
        raise SystemExit(1)


def main(argv: list[str] | None = None) -> None:
    raise SystemExit(run(argv))


def run(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return _dispatch(args)
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 1
        return int(code)
    except BindError as exc:
        print(f"vesper-bind: {exc}", file=sys.stderr)
        return 1


def build_parser() -> Parser:
    parser = Parser(
        prog="vesper-bind",
        description=(
            f"vesper-bind {__version__}. Unofficial DagzTagz CLI. "
            "Binds local artifacts into one receipt. Does not call a model."
        ),
    )
    parser.add_argument("--version", action="version", version=f"vesper-bind {__version__}")
    parser.add_argument("--dry-run", action="store_true", help="print a receipt and write nothing")
    parser.add_argument("--hypothesis", help="hypothesis JSON file")
    parser.add_argument("--scaffold-run", help="Dagz-Scaffold run directory")
    sub = parser.add_subparsers(dest="command")

    bind = sub.add_parser("bind", help="write one receipt when both inputs pass")
    bind.add_argument("--hypothesis", required=True)
    bind.add_argument("--scaffold-run", required=True)
    bind.add_argument("--out", required=True)
    bind.add_argument("--vesper-workspace", default=None)

    verify = sub.add_parser("verify", help="recompute digests and check mode 0600")
    verify.add_argument("receipt")

    show = sub.add_parser("show", help="print the receipt in the stable text layout")
    show.add_argument("receipt")
    return parser


def _dispatch(args: argparse.Namespace) -> int:
    if args.dry_run and args.command:
        print("vesper-bind: --dry-run does not take a subcommand", file=sys.stderr)
        return 1
    if args.command is None:
        if not args.dry_run:
            print("vesper-bind: choose --dry-run, bind, verify, or show", file=sys.stderr)
            return 1
        if not args.hypothesis or not args.scaffold_run:
            print(
                "vesper-bind: --dry-run requires --hypothesis and --scaffold-run",
                file=sys.stderr,
            )
            return 1
        receipt = _receipt_from_inputs(Path(args.hypothesis), Path(args.scaffold_run), None)
        sys.stdout.write(receipt.to_json())
        return 0
    if args.command == "bind":
        return _bind(args)
    if args.command == "verify":
        return _verify(Path(args.receipt))
    if args.command == "show":
        return _show(Path(args.receipt))
    print("vesper-bind: choose --dry-run, bind, verify, or show", file=sys.stderr)
    return 1


def _bind(args: argparse.Namespace) -> int:
    hypothesis = Path(args.hypothesis)
    scaffold = Path(args.scaffold_run)
    # Validate both inputs before any write. A missing workspace also writes nothing.
    bound = load_inputs(hypothesis, scaffold)
    note_id: str | None = None
    state_bytes: bytes | None = None
    if args.vesper_workspace:
        note_id, state_bytes = prepare_note(Path(args.vesper_workspace), int(time.time()))
    created = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = bound.hypothesis
    receipt = build_receipt(
        created_utc=created,
        hypothesis_path=record.path,
        hypothesis_size=record.size,
        hypothesis_mtime_utc=record.mtime_utc,
        hypothesis_sha256=record.sha256,
        scaffold_path=bound.scaffold_path,
        plan_md_sha256=bound.plan_sha256,
        evidence_md_sha256=bound.evidence_sha256,
        critic_md_sha256=bound.critic_sha256,
        score_json_sha256=bound.score_sha256,
        pass_flags=bound.pass_flags,
        vesper_note_id=note_id,
    )
    out_path = abspath(Path(args.out))
    existed = out_path.exists() or out_path.is_symlink()
    out = ensure_private_dir(out_path)
    path: Path | None = None
    try:
        path = atomic_create(out, _filename(receipt.created_utc), receipt.to_json().encode("utf-8"))
        if state_bytes is not None and args.vesper_workspace:
            commit_note(Path(args.vesper_workspace), state_bytes)
    except Exception:
        if path is not None:
            _unlink_quiet(path)
        if not existed:
            _remove_empty_dir(out)
        raise
    sys.stdout.write(str(path) + "\n")
    return 0


def _remove_empty_dir(path: Path) -> None:
    try:
        if path.is_dir() and not path.is_symlink() and not any(path.iterdir()):
            os.rmdir(path)
    except OSError:
        pass


def _unlink_quiet(path: Path) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _receipt_from_inputs(hypothesis: Path, scaffold: Path, note_id: str | None) -> Receipt:
    bound = load_inputs(hypothesis, scaffold)
    created = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = bound.hypothesis
    return build_receipt(
        created_utc=created,
        hypothesis_path=record.path,
        hypothesis_size=record.size,
        hypothesis_mtime_utc=record.mtime_utc,
        hypothesis_sha256=record.sha256,
        scaffold_path=bound.scaffold_path,
        plan_md_sha256=bound.plan_sha256,
        evidence_md_sha256=bound.evidence_sha256,
        critic_md_sha256=bound.critic_sha256,
        score_json_sha256=bound.score_sha256,
        pass_flags=bound.pass_flags,
        vesper_note_id=note_id,
    )


def _filename(created_utc: str) -> str:
    # created_utc is YYYY-MM-DDTHH:MM:SSZ. The file name uses the compact form.
    compact = (
        created_utc[0:4]
        + created_utc[5:7]
        + created_utc[8:10]
        + "T"
        + created_utc[11:13]
        + created_utc[14:16]
        + created_utc[17:19]
        + "Z"
    )
    return f"{compact}-receipt.json"


def _verify(path: Path) -> int:
    _require_mode_0600(path)
    receipt = _load_receipt(path)
    hypothesis = digest_if_present(Path(receipt.hypothesis_path))
    if hypothesis is not None and hypothesis != receipt.hypothesis_sha256:
        raise BindError("digest mismatch: hypothesis")
    root = Path(receipt.scaffold_path)
    for name, attr in _SCAFFOLD_DIGESTS:
        current = digest_if_present(root / name)
        expected = getattr(receipt, attr)
        if current is not None and current != expected:
            raise BindError(f"digest mismatch: {name}")
    sys.stdout.write("verify ok\n")
    return 0


def _show(path: Path) -> int:
    receipt = _load_receipt(path)
    sys.stdout.write(receipt.render())
    return 0


def _load_receipt(path: Path) -> Receipt:
    absolute = abspath(path)
    refuse_forbidden(absolute)
    if absolute.is_symlink():
        raise BindError("receipt is not mode 0600")
    if not absolute.is_file():
        raise BindError("receipt is unreadable")
    record = read_regular(absolute)
    try:
        text = record.data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BindError("receipt is unreadable") from exc
    return load_text(text)


def _require_mode_0600(path: Path) -> None:
    absolute = abspath(path)
    refuse_forbidden(absolute)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        fd = os.open(absolute, flags)
    except OSError as exc:
        raise BindError("receipt is not mode 0600") from exc
    try:
        info = os.fstat(fd)
        mode = stat.S_IMODE(info.st_mode)
        if not stat.S_ISREG(info.st_mode) or mode != 0o600:
            raise BindError("receipt is not mode 0600")
    finally:
        os.close(fd)
