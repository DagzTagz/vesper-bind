"""Jail reads and atomic writes. Key paths are refused before open."""

from __future__ import annotations

import hashlib
import os
import secrets
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from vesper_bind.errors import BindError

MAX_BYTES = 8 * 1024 * 1024
_OPEN_READ = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_OPEN_WRITE = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC


@dataclass(frozen=True)
class FileRecord:
    path: str
    size: int
    mtime_utc: str
    sha256: str
    data: bytes


def refuse_forbidden(path: Path) -> None:
    """Never open identity/, a private key, or hmac.key."""
    parts = [part for part in path.parts if part not in {"/", ""}]
    if "identity" in parts:
        raise BindError("refusing to open identity")
    name = path.name
    if name == "hmac.key" or name.endswith(".priv"):
        raise BindError("refusing to open a key file")


def abspath(path: Path) -> Path:
    return Path(os.path.abspath(path))


def realpath(path: Path) -> Path:
    return Path(os.path.realpath(path))


def inside(root: Path, candidate: Path) -> bool:
    try:
        realpath(candidate).relative_to(realpath(root))
    except ValueError:
        return False
    return True


def assert_symlinks_stay(path: Path) -> None:
    """Reject a symlink whose target leaves the directory that contains the link."""
    absolute = abspath(path)
    current = Path(absolute.anchor)
    for part in absolute.relative_to(absolute.anchor).parts:
        current = current / part
        if not current.is_symlink():
            continue
        target = realpath(current)
        refuse_forbidden(target)
        try:
            target.relative_to(realpath(current.parent))
        except ValueError as exc:
            raise BindError("symlink resolves outside the directory") from exc


def format_mtime(stamp: float) -> str:
    moment = datetime.fromtimestamp(int(stamp), timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def read_regular(path: Path) -> FileRecord:
    """Read a regular file that is already known not to be a symlink."""
    refuse_forbidden(path)
    assert_symlinks_stay(path)
    try:
        fd = os.open(path, _OPEN_READ)
    except OSError as exc:
        raise BindError("file is unreadable") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise BindError("file is unreadable")
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        size = 0
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            size += len(block)
            if size > MAX_BYTES:
                raise BindError("file is larger than 8 MiB")
            digest.update(block)
            chunks.append(block)
        return FileRecord(
            path=str(path),
            size=size,
            mtime_utc=format_mtime(info.st_mtime),
            sha256=digest.hexdigest(),
            data=b"".join(chunks),
        )
    finally:
        os.close(fd)


def read_jailed_file(root: Path, name: str) -> FileRecord:
    """Read root/name. A symlink that leaves root is an error."""
    if name != Path(name).name or name in {".", ".."}:
        raise BindError("scaffold file is missing")
    directory = abspath(root)
    refuse_forbidden(directory)
    assert_symlinks_stay(directory)
    # The run directory itself must be a real directory. A symlink root
    # would widen the jail to the link target, including a link to its parent.
    if directory.is_symlink():
        raise BindError("symlink resolves outside the directory")
    if not directory.is_dir():
        raise BindError("scaffold run is missing")
    jail = realpath(directory)
    refuse_forbidden(jail)
    candidate = directory / name
    if not candidate.exists() and not candidate.is_symlink():
        if name == "score.json":
            raise BindError("scaffold score.json is missing")
        raise BindError(f"scaffold file is missing: {name}")
    target = realpath(candidate)
    refuse_forbidden(target)
    try:
        target.relative_to(jail)
    except ValueError as exc:
        raise BindError("symlink resolves outside the directory") from exc
    if not target.is_file():
        raise BindError(f"scaffold file is unreadable: {name}")
    # Open the real file. The jail check above is what blocks an outside target.
    return read_regular(target)


def read_user_file(path: Path, *, missing: str, unreadable: str) -> FileRecord:
    """Read one file. Its real path must stay inside its parent directory."""
    absolute = abspath(path)
    refuse_forbidden(absolute)
    assert_symlinks_stay(absolute)
    parent = absolute.parent
    if not parent.is_dir() and not absolute.exists():
        raise BindError(missing)
    if not absolute.exists() and not absolute.is_symlink():
        raise BindError(missing)
    jail = realpath(parent)
    target = realpath(absolute)
    refuse_forbidden(target)
    try:
        target.relative_to(jail)
    except ValueError as exc:
        raise BindError("symlink resolves outside the directory") from exc
    if not target.is_file():
        raise BindError(unreadable)
    return read_regular(target)


def digest_if_present(path: Path) -> str | None:
    """Hash a stored path. Missing paths are skipped. Escapes are errors."""
    absolute = abspath(path)
    assert_symlinks_stay(absolute)
    if not absolute.exists() and not absolute.is_symlink():
        return None
    parent = absolute.parent
    target = realpath(absolute)
    refuse_forbidden(absolute)
    refuse_forbidden(target)
    try:
        target.relative_to(realpath(parent))
    except ValueError as exc:
        raise BindError("symlink resolves outside the directory") from exc
    if not target.is_file():
        raise BindError("file is unreadable")
    return read_regular(target).sha256


def ensure_private_dir(path: Path) -> Path:
    """Create or reuse a real directory and force mode 0700. Do not follow a symlink."""
    absolute = abspath(path)
    refuse_forbidden(absolute)
    assert_symlinks_stay(absolute)
    if absolute.is_symlink():
        raise BindError("symlink resolves outside the directory")
    parent = absolute.parent
    if not parent.is_dir():
        raise BindError("output directory cannot be created")
    created = False
    try:
        if not absolute.exists():
            os.mkdir(absolute, 0o700)
            created = True
        if absolute.is_symlink() or not absolute.is_dir():
            raise BindError("output directory is not a directory")
        fd = os.open(absolute, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            os.fchmod(fd, 0o700)
            mode = stat.S_IMODE(os.fstat(fd).st_mode)
            if mode != 0o700:
                raise BindError("output directory is not mode 0700")
        finally:
            os.close(fd)
    except Exception:
        if created:
            _remove_empty_dir(absolute)
        raise
    return absolute


def _remove_empty_dir(path: Path) -> None:
    try:
        if path.is_dir() and not path.is_symlink() and not any(path.iterdir()):
            os.rmdir(path)
    except OSError:
        pass


def _tmp_path(directory: Path, filename: str) -> Path:
    token = secrets.token_hex(6)
    return directory / f".{filename}.{os.getpid()}.{token}.tmp"


def _write_new(tmp: Path, data: bytes) -> None:
    try:
        fd = os.open(tmp, _OPEN_WRITE, 0o600)
    except OSError as exc:
        raise BindError("receipt write failed") from exc
    try:
        os.fchmod(fd, 0o600)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise BindError("receipt write failed")
            view = view[written:]
        os.fchmod(fd, 0o600)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise BindError("receipt is not mode 0600")
        os.fsync(fd)
    except OSError as exc:
        raise BindError("receipt write failed") from exc
    finally:
        os.close(fd)


def _fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _unlink_quiet(path: Path) -> None:
    try:
        if path.is_symlink() or path.exists():
            os.unlink(path)
    except OSError:
        pass


def atomic_create(directory: Path, filename: str, data: bytes) -> Path:
    """Create filename in directory. Fail if the name exists. Leave no temp file.

    The bytes are fsynced, then published with link(2). link does not replace
    an existing name, which rename(2) would.
    """
    if "/" in filename or filename in {"", ".", ".."} or filename.startswith("."):
        raise BindError("receipt name is invalid")
    final = directory / filename
    if final.exists() or final.is_symlink():
        raise BindError("receipt already exists")
    tmp = _tmp_path(directory, filename)
    linked = False
    try:
        _write_new(tmp, data)
        try:
            os.link(tmp, final)
        except OSError as exc:
            raise BindError("receipt write failed") from exc
        linked = True
        _fsync_dir(directory)
        return final
    except BindError:
        if linked:
            _unlink_quiet(final)
        raise
    except OSError as exc:
        if linked:
            _unlink_quiet(final)
        raise BindError("receipt write failed") from exc
    finally:
        _unlink_quiet(tmp)


def atomic_replace(directory: Path, filename: str, data: bytes) -> None:
    """Replace a regular file in directory. Refuse a symlink. Leave no temp file."""
    final = directory / filename
    if final.is_symlink():
        raise BindError("refusing to write through a symlink")
    if not final.is_file():
        raise BindError("workspace state cannot take a note")
    tmp = _tmp_path(directory, filename)
    try:
        _write_new(tmp, data)
        os.replace(tmp, final)
        _fsync_dir(directory)
    except BindError:
        raise
    except OSError as exc:
        raise BindError("workspace state cannot take a note") from exc
    finally:
        _unlink_quiet(tmp)
