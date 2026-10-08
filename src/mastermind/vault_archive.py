"""Plain Obsidian Vault ZIPs: bounded validation and private staging, never live extraction."""
import os
import stat
import struct
import zipfile
import zlib
from datetime import datetime
from pathlib import Path

from .deadline import check, snapshot_budget
from .errors import DomainError
from .fs import directory_inventory, file_inventory, name_key, resolve, safe_relative, sha_file
from .spool import BoundedWriter, copy_bounded, private_open

FORMAT = "obsidian-vault-zip/v1"
CENTRAL_LIMIT = 64 * 1024**2


def invalid(message="Choose a complete Obsidian Vault ZIP with its contents at the archive root."):
    return DomainError("INVALID_VAULT_ARCHIVE", message, 422)


def directory_budget(source, config):
    """Reject oversized central directories before ZipFile allocates its member list."""
    size = source.stat().st_size
    if not 0 < size <= config.max_backup_bytes:
        raise DomainError("SIZE_LIMIT", "The Vault ZIP exceeds the upload limit.", 413)
    with source.open("rb") as stream:
        stream.seek(max(0, size-65557))
        tail = stream.read(65557)
        offset = tail.rfind(b"PK\x05\x06")
        if offset < 0 or len(tail)-offset < 22:
            raise invalid()
        _, disk, start_disk, disk_count, count, central_size, central_offset, comment_size = struct.unpack_from("<4s4H2LH", tail, offset)
        if disk or start_disk or disk_count != count or len(tail)-offset != 22+comment_size:
            raise invalid("Split ZIPs and trailing data are not supported.")
        end = size-len(tail)+offset
        stream.seek(max(0, end-20))
        locator = stream.read(20)
        # ZIP64 may be used before the classic fields overflow. Conversely,
        # exactly 65,535 entries can still use a classic directory (Python does).
        zip64 = end >= 20 and locator[:4] == b"PK\x06\x07"
        if not zip64 and (central_size == 0xffffffff or central_offset == 0xffffffff):
            raise invalid("The ZIP64 directory is invalid.")
        if zip64:
            _, disk, record_offset, disks = struct.unpack("<4sLQL", locator)
            if disk or disks != 1 or record_offset > end-76:
                raise invalid("The ZIP64 directory is invalid.")
            stream.seek(record_offset)
            record = stream.read(56)
            if len(record) != 56:
                raise invalid()
            signature, length, _, _, disk, start_disk, disk_count, count, central_size, central_offset = struct.unpack("<4sQ2H2L4Q", record)
            if signature != b"PK\x06\x06" or length < 44 or record_offset+length+12 != end-20 or disk or start_disk or disk_count != count:
                raise invalid("The ZIP64 directory is invalid.")
            end = record_offset
        if count > config.max_archive_entries or central_size > CENTRAL_LIMIT:
            raise DomainError("SIZE_LIMIT", "The Vault ZIP directory exceeds its limit.", 413)
        if central_offset+central_size != end:
            raise invalid("The ZIP directory does not match its contents.")


def members(archive, config):
    entries = archive.infolist()
    if len(entries) > config.max_archive_entries:
        raise invalid("The Vault ZIP contains too many entries.")
    paths, nodes, total = {}, {}, 0
    for item in entries:
        check()
        path = safe_relative(item.filename[:-1] if item.is_dir() else item.filename)
        if item.orig_filename != item.filename:
            raise invalid("The ZIP reader normalized an unsafe member name.")
        mode = stat.S_IFMT(item.external_attr >> 16)
        if item.flag_bits & 1 or item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) or mode not in (
            (0, stat.S_IFDIR) if item.is_dir() else (0, stat.S_IFREG)
        ):
            raise invalid("Encrypted, linked or unsupported ZIP entries are not accepted.")
        if item.is_dir() and item.file_size or item.file_size > config.max_backup_bytes or item.file_size > max(1, item.compress_size)*1000:
            raise DomainError("SIZE_LIMIT", "A Vault ZIP member exceeds its expansion limit.", 413)
        total += item.file_size
        if total > config.max_expanded_bytes:
            raise DomainError("SIZE_LIMIT", "The expanded Vault exceeds its limit.", 413)
        key = name_key(path)
        if key in paths:
            raise invalid("Duplicate or case/Unicode-aliased ZIP entries are not accepted.")
        parts = path.split("/")
        for index in range(1, len(parts)+1):
            name = "/".join(parts[:index])
            identity = (name, index < len(parts) or item.is_dir())
            if name_key(name) in nodes and nodes[name_key(name)] != identity:
                raise invalid("Vault ZIP file and directory paths conflict.")
            nodes[name_key(name)] = identity
            if len(nodes) > config.max_archive_entries:
                raise DomainError("SIZE_LIMIT", "The Vault ZIP tree exceeds its entry limit.", 413)
        paths[key] = (path, item)
    files = [path for path, item in paths.values() if not item.is_dir()]
    # A single enclosing folder is unambiguous only when it contains .obsidian.
    # Never strip a user's ordinary root/ notes folder merely because it is alone.
    wrapper = files[0].split("/")[0] if files else ""
    prefix = wrapper+"/" if all(path.startswith(wrapper+"/") for path in files) and any(
        path.startswith(wrapper+"/.obsidian/") for path in files) and all(
        path == wrapper or path.startswith(wrapper+"/") for path, _ in paths.values()) else ""
    result = [(path[len(prefix):] if prefix else path, item) for path, item in paths.values() if not (prefix and path == wrapper)]
    if {path for path, item in result if not item.is_dir()} == {"manifest.json", "payload.age"}:
        raise invalid("Use Restore ZIP snapshot for an encrypted service recovery archive.")
    return result, {"format": FORMAT, "files": len(files), "directories": sum(item.is_dir() for _, item in result),
                    "expanded_bytes": total, "root_prefix": prefix}


class VaultArchive:
    def __init__(self, backup):
        self.backup, self.config = backup, backup.config

    def create(self, destination):
        """Writer-coordinated raw Vault copy; no Shell settings or recovery keys."""
        with snapshot_budget(), self.backup.spool.operation(self.backup.estimate()*3) as folder:
            with self.backup.coordinator.boundary(), self.backup.state.lock:
                tree = self.backup.copy_vault(folder)
            # Fast deflate avoids excessive CPU work on already compressed attachments.
            with private_open(destination) as stream:
                writer = BoundedWriter(stream, self.config.max_backup_bytes)
                with zipfile.ZipFile(writer, "w", zipfile.ZIP_DEFLATED, compresslevel=1, strict_timestamps=False) as archive:
                    for relative, path in directory_inventory(tree):
                        check()
                        archive.write(path, relative+"/")
                    for relative, path in file_inventory(tree):
                        check()
                        archive.write(path, relative)
                stream.flush()
                os.fsync(stream.fileno())
        return {"size": destination.stat().st_size, "sha256": sha_file(destination)}

    def describe(self, source):
        source = Path(source)
        try:
            directory_budget(source, self.config)
            with zipfile.ZipFile(source) as archive:
                _, info = members(archive, self.config)
                return info
        except (zipfile.BadZipFile, ValueError, OverflowError, struct.error):
            raise invalid() from None

    def unpack(self, source, folder):
        source = Path(source)
        tree = folder / "checked"
        vault = tree / "vault"
        vault.mkdir(mode=0o700, parents=True)
        notes, names = 0, set()
        try:
            directory_budget(source, self.config)
            with zipfile.ZipFile(source) as archive:
                entries, info = members(archive, self.config)
                for relative, item in entries:
                    check()
                    destination = resolve(vault, relative, internal=True)
                    if item.is_dir():
                        destination.mkdir(mode=0o700, parents=True, exist_ok=True)
                        continue
                    with archive.open(item) as src, private_open(destination) as dst:
                        size, digest = copy_bounded(src, dst, item.file_size)
                    if size != item.file_size or sha_file(destination) != digest:
                        raise invalid("A Vault ZIP member failed its integrity check.")
                    if os.name == "posix":
                        os.chmod(destination, (item.external_attr >> 16 & 0o777) or 0o600)
                    # DOS ZIP timestamps have local-time semantics and no zone field.
                    modified = datetime(*item.date_time).astimezone().timestamp()
                    os.utime(destination, (modified, modified))
                    if relative.lower().endswith(".md") and not any(part.startswith(".") for part in relative.split("/")):
                        if size > self.config.max_note_bytes:
                            raise DomainError("NOTE_TOO_LARGE", "A restored note exceeds the supported size.", 413)
                        destination.read_text("utf-8")  # Validate before any live-state replacement.
                        key = name_key(destination.stem)
                        if key in names:
                            raise DomainError("DUPLICATE_BASENAME", "The Vault contains conflicting note names.", 422)
                        names.add(key)
                        notes += 1
            return tree, {**info, "notes": notes}
        except (zipfile.BadZipFile, EOFError, ValueError, UnicodeError, OverflowError, RuntimeError, zlib.error, struct.error):
            raise invalid("The Vault ZIP is damaged or contains an unreadable note.") from None

    def inspect(self, source):
        info = self.describe(source)
        with snapshot_budget(), self.backup.spool.operation(info["expanded_bytes"]+64*1024**2) as folder:
            _, info = self.unpack(source, folder)
        return {**info, "sessions_will_be_invalidated": True, "shell_settings_preserved": True,
                "shared_links_will_be_revoked": True}
