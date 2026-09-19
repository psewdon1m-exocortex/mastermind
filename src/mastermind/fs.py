"""Filesystem primitives. No caller-controlled path may escape a declared root."""
import hashlib
import json
import os
import re
import stat
import unicodedata
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from .deadline import check
from .errors import DomainError

WINDOWS_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", re.IGNORECASE)


def name_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def safe_relative(value: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 4096:
        raise DomainError("UNSAFE_PATH", "A bounded relative path is required.")
    if "\\" in value or "\0" in value or ":" in value or value.startswith("/"):
        raise DomainError("UNSAFE_PATH", "Only relative forward-slash paths are accepted.")
    parts = value.split("/")
    if any(p in ("", ".", "..") or p.endswith((" ", ".")) or any(ord(c) < 32 for c in p)
           or WINDOWS_RESERVED.match(p) for p in parts):
        raise DomainError("UNSAFE_PATH", "The path contains an unsafe component.")
    if len(parts) > 64:
        raise DomainError("UNSAFE_PATH", "Path depth exceeds the supported limit.")
    return str(PurePosixPath(value))


def resolve(root: Path, relative: str, *, internal: bool = False) -> Path:
    relative = safe_relative(relative)
    if not internal and any(p.startswith(".") for p in relative.split("/")):
        raise DomainError("RESERVED_PATH", "Hidden application paths are not exposed.")
    current = root
    if root.is_symlink() or root.is_junction():
        raise DomainError("UNSAFE_PATH", "The root must not be a symbolic link.")
    for part in relative.split("/"):
        current = current / part
        if current.is_symlink() or current.is_junction():
            raise DomainError("UNSAFE_PATH", "Symbolic links are not followed.")
        if current.exists():
            st = current.stat(follow_symlinks=False)
            if not stat.S_ISDIR(st.st_mode) and not stat.S_ISREG(st.st_mode):
                raise DomainError("UNSAFE_PATH", "Special files are not accepted.")
            if stat.S_ISREG(st.st_mode) and st.st_nlink > 1:
                raise DomainError("UNSAFE_PATH", "Hard-linked files are not accepted.")
    if not current.resolve().is_relative_to(root.resolve()):
        raise DomainError("UNSAFE_PATH", "The resolved path is outside the root.")
    return current


def sha_file(path: Path) -> str | None:
    check()
    if not path.is_file():
        return None
    with path.open("rb") as stream:
        return stream_digest(stream)


def stream_digest(stream):
    digest = hashlib.sha256()
    check()
    while block := stream.read(1024 * 1024):
        check()
        digest.update(block)
    check()
    return digest.hexdigest()


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sync_dir(path: Path):
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def atomic_write(path: Path, value: bytes, *, create: bool = False, mode: int = 0o600):
    import secrets
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / (".mastermind-" + secrets.token_hex(12))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(value)
            out.flush()
            os.fsync(out.fileno())
        if create:
            os.link(temporary, path)
            temporary.unlink()
        else:
            os.replace(temporary, path)
        sync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: Path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")).encode("utf-8"))


def file_inventory(root: Path, *, include_hidden=True):
    """Yield regular files, validating hidden user data without reading its content."""
    for directory, dirs, names in os.walk(root, followlinks=False):
        check()
        if not include_hidden:
            dirs[:] = [name for name in dirs if not name.startswith(".")]
            names = [name for name in names if not name.startswith(".")]
        dirs.sort()
        names.sort()
        for name in dirs:
            candidate = Path(directory) / name
            if candidate.is_symlink() or candidate.is_junction():
                raise DomainError("UNSAFE_PATH", "Vault contains a symbolic directory.")
        for name in names:
            check()
            relative = (Path(directory) / name).relative_to(root).as_posix()
            path = resolve(root, relative, internal=True)
            yield relative, path


def directory_inventory(root: Path):
    for directory, dirs, _ in os.walk(root, followlinks=False):
        check()
        dirs.sort()
        for name in dirs:
            check()
            relative = (Path(directory) / name).relative_to(root).as_posix()
            yield relative, resolve(root, relative, internal=True)


def durable_tree(root: Path):
    for _, path in file_inventory(root):
        with path.open("r+b" if os.name == "nt" else "rb") as stream:
            os.fsync(stream.fileno())
    for _, path in reversed(list(directory_inventory(root))):
        sync_dir(path)
    sync_dir(root)
    check()


@contextmanager
def parent_descriptor(root: Path, relative: str, *, internal=False, create=False):
    """Walk directory descriptors without following a replacement symlink on Linux."""
    relative = safe_relative(relative)
    if not internal and any(part.startswith(".") for part in relative.split("/")):
        raise DomainError("RESERVED_PATH", "Hidden application paths are not exposed.")
    if os.name != "posix":
        path = resolve(root, relative, internal=internal)
        if create:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        yield None, path
        return
    descriptor = None
    try:
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for component in relative.split("/")[:-1]:
            if create:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                    os.fsync(descriptor)
                except FileExistsError:
                    pass
            following = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = following
        yield descriptor, relative.split("/")[-1]
    except OSError as error:
        import errno
        if error.errno in (errno.ELOOP, errno.ENOTDIR):
            raise DomainError("UNSAFE_PATH", "A path component is not an ordinary directory or file.") from None
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)


@contextmanager
def open_under(root: Path, relative: str, *, internal=False):
    with parent_descriptor(root, relative, internal=internal) as (directory, name):
        descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise DomainError("UNSAFE_PATH", "Only regular, singly linked files are accepted.")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                yield stream
        finally:
            os.close(descriptor)


def sha_under(root: Path, relative: str, *, internal=False):
    try:
        with open_under(root, relative, internal=internal) as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except FileNotFoundError:
        return None


@contextmanager
def write_existing_under(root: Path, relative: str):
    """Stream into a private reserved ordinary file without following or truncating links."""
    with parent_descriptor(root, relative) as (directory, name):
        descriptor = os.open(name, os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise DomainError("UNSAFE_PATH", "The upload target is not an ordinary private file.")
            os.ftruncate(descriptor, 0)
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                yield stream
                stream.flush()
                os.fsync(descriptor)
        finally:
            os.close(descriptor)


def atomic_write_under(root: Path, relative: str, value: bytes, *, create=False, internal=False):
    import secrets
    with parent_descriptor(root, relative, internal=internal, create=True) as (directory, name):
        if directory is None:
            return atomic_write(name, value, create=create)
        try:
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise DomainError("UNSAFE_PATH", "The destination is not an ordinary file.")
        except FileNotFoundError:
            pass
        temporary = ".mastermind-" + secrets.token_hex(12)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            if create:
                os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            else:
                os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
            os.fsync(directory)


def unlink_under(root: Path, relative: str):
    with parent_descriptor(root, relative) as (directory, name):
        os.unlink(name, dir_fd=directory)
        if directory is not None:
            os.fsync(directory)


def atomic_stream_under(root: Path, relative: str, source, expected_digest: str, limit: int, *, create=False, deadline=None):
    """Publish a verified large file without following links or retaining it in RAM."""
    import secrets
    import time
    with parent_descriptor(root, relative, create=True) as (directory, name):
        try:
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise DomainError("UNSAFE_PATH", "The destination is not an ordinary file.")
        except FileNotFoundError:
            pass
        temporary = ".mastermind-" + secrets.token_hex(12)
        if directory is None:
            temporary = name.parent / temporary
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                             0o600, dir_fd=directory)
        try:
            digest, size = hashlib.sha256(), 0
            with os.fdopen(descriptor, "wb") as output:
                while chunk := source.read(1024**2):
                    if deadline is not None and time.monotonic() > deadline:
                        raise DomainError("VAULT_BUSY", "The native operation exceeded its pause deadline.", 423)
                    size += len(chunk)
                    if size > limit:
                        raise DomainError("SIZE_LIMIT", "The recovery file exceeds its limit.", 413)
                    digest.update(chunk)
                    output.write(chunk)
                if digest.hexdigest() != expected_digest:
                    raise DomainError("RECOVERY_REQUIRED", "Recovery payload failed integrity.", 503)
                output.flush()
                os.fsync(output.fileno())
            if create:
                os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            else:
                os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
            if directory is not None:
                os.fsync(directory)
            else:
                sync_dir(name.parent)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass


def remove_private_tree(path: Path, parent: Path):
    """Remove a generated staging tree, including preserved read-only plugin files."""
    import shutil
    if path.is_symlink() or path.is_junction() or path.parent.resolve() != parent.resolve():
        raise DomainError("UNSAFE_PATH", "Cleanup target is outside its private staging parent.", 503)
    # rmtree's fd-based implementation does not follow links; chmod only actual entries.
    for directory, dirs, files in os.walk(path, followlinks=False):
        for candidate in [Path(directory), *(Path(directory)/name for name in [*dirs, *files])]:
            if not candidate.is_symlink() and not candidate.is_junction():
                os.chmod(candidate, 0o700 if candidate.is_dir() else 0o600)
    shutil.rmtree(path)
