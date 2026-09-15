"""One streaming, encrypted logical backup format for manual, Neptune and Updater use."""
import base64
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import ijson
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from . import __version__
from .crypto_stream import transform
from .deadline import check, snapshot_budget
from .errors import DomainError
from .fs import (
    directory_inventory,
    file_inventory,
    name_key,
    open_under,
    resolve,
    safe_relative,
    sha_file,
    stream_digest,
)
from .spool import Spool, copy_bounded, private_open
from .state import MANDATORY_TABLES, State

FORMAT = "mastermind-backup/v1"
STATE_PART_BYTES = 4 * 1024**2
STATE_RECORD_BYTES = 1024**2
PART = re.compile(r"state/([a-z_]+)-([0-9]{6})\.json$")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def checked_json(data):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite number")))


def zip_members(archive, config, *, outer=False):
    """Validate the complete central directory before any extraction."""
    entries = archive.infolist()
    if len(entries) > (2 if outer else config.max_archive_entries):
        raise DomainError("INVALID_ARCHIVE", "Archive has too many members.", 422)
    seen, total, result = set(), 0, {}
    for item in entries:
        path = safe_relative(item.orig_filename)
        if path != item.filename:
            raise DomainError("INVALID_ARCHIVE", "Archive member name was normalized by the ZIP reader.", 422)
        key = name_key(path)
        mode = item.external_attr >> 16
        if key in seen or item.is_dir() or item.flag_bits & 1 \
                or stat.S_IFMT(mode) not in (0, stat.S_IFREG):
            raise DomainError("INVALID_ARCHIVE", "Duplicate, linked or unsupported archive member.", 422)
        seen.add(key)
        if item.file_size > config.max_backup_bytes or item.file_size > max(1, item.compress_size) * 1000:
            raise DomainError("INVALID_ARCHIVE", "Archive member exceeds size or expansion limits.", 413)
        total += item.file_size
        if total > (config.max_backup_bytes if outer else config.max_expanded_bytes):
            raise DomainError("INVALID_ARCHIVE", "Archive expansion exceeds its limit.", 413)
        result[path] = item
    if outer and set(result) != {"manifest.json", "payload.age"}:
        raise DomainError("INVALID_ARCHIVE", "The recovery wrapper has unexpected members.", 422)
    # Reject a file used as the parent of another entry, including Unicode/case aliases.
    for path in result:
        parts = path.split("/")
        if any(name_key("/".join(parts[:i])) in seen for i in range(1, len(parts))):
            raise DomainError("INVALID_ARCHIVE", "Archive paths conflict.", 422)
    return result


class Backup:
    def __init__(self, config, state, coordinator, vault, secret_store, audit):
        self.config, self.state, self.coordinator, self.vault = config, state, coordinator, vault
        self.secrets, self.audit = secret_store, audit
        self.spool = Spool(config)

    def estimate(self):
        return sum(path.stat().st_size for _, path in file_inventory(self.config.vault)) \
            + self.state.path.stat().st_size + 16*1024**2

    def signing_key(self):
        try:
            return Ed25519PrivateKey.from_private_bytes(base64.b64decode(
                self.secrets.read("backup_signing_private"), validate=True))
        except (ValueError, TypeError):
            raise DomainError("SECRET_UNAVAILABLE", "The backup signing key is invalid.", 503) from None

    def trust_key(self):
        try:
            return Ed25519PublicKey.from_public_bytes(base64.b64decode(
                self.secrets.read("backup_signing_public"), validate=True))
        except (ValueError, TypeError):
            raise DomainError("SECRET_UNAVAILABLE", "The backup trust key is invalid.", 503) from None

    def snapshot(self, folder, *, inside_boundary=False):
        if not inside_boundary:
            with snapshot_budget(), self.coordinator.boundary():
                return self.snapshot(folder, inside_boundary=True)
        with snapshot_budget():
            return self._snapshot(folder)

    def _snapshot(self, folder):
        self.vault.index(force=True)
        tree = folder / "vault"
        tree.mkdir(mode=0o700)
        for relative, _ in directory_inventory(self.config.vault):
            destination = resolve(tree, relative, internal=True)
            destination.mkdir(mode=0o700, parents=True, exist_ok=True)
        for relative, source in file_inventory(self.config.vault):
            destination = resolve(tree, relative, internal=True)
            with open_under(self.config.vault, relative, internal=True) as src, private_open(destination) as dst:
                size, digest = copy_bounded(src, dst, self.config.max_backup_bytes)
            if source.stat().st_size != size or sha_file(source) != digest:
                raise DomainError("VAULT_BUSY", "A file changed during snapshot.", 423)
            shutil.copystat(source, destination, follow_symlinks=False)
        if os.name == "posix":
            for relative, path in reversed(list(directory_inventory(tree))):
                os.chmod(path, (self.config.vault / relative).stat().st_mode & 0o777)
        # A new/deleted file from an uncontrolled writer invalidates the snapshot too.
        if {rel for rel, _ in directory_inventory(tree)} != \
                {rel for rel, _ in directory_inventory(self.config.vault)} or \
                {rel: sha_file(p) for rel, p in file_inventory(tree)} != \
                {rel: sha_file(p) for rel, p in file_inventory(self.config.vault)}:
            raise DomainError("VAULT_BUSY", "Vault inventory changed during snapshot.", 423)
        database = folder / "snapshot.sqlite3"
        with self.state.lock, closing(sqlite3.connect(database)) as copy:
            self.state.db.backup(copy, pages=256, progress=lambda *_: check())
        os.chmod(database, 0o600)
        generation = self.state.one("SELECT value FROM metadata WHERE key='generation'")["value"]
        check()
        return {"boundary": datetime.now(UTC).isoformat(), "generation": int(generation)}

    def export_state(self, database, directory):
        directory.mkdir(mode=0o700)
        records = {}
        with closing(sqlite3.connect(database)) as db:
            db.row_factory = sqlite3.Row
            for table in MANDATORY_TABLES:
                index, stream, size, count, total = 0, None, 0, 0, 0
                try:
                    for row in db.execute(f'SELECT * FROM "{table}" ORDER BY rowid'):
                        check()
                        data = canonical(dict(row))
                        if len(data) > STATE_RECORD_BYTES:
                            raise DomainError("STATE_LIMIT", "A state record exceeds the backup limit.", 413)
                        if stream is None or size + len(data) + 2 > STATE_PART_BYTES:
                            if stream:
                                stream.write(b"]")
                                stream.close()
                                records[f"state/{table}-{index:06}.json"] = count
                                index += 1
                            stream = private_open(directory / f"{table}-{index:06}.json")
                            stream.write(b"[")
                            size, count = 1, 0
                        if count:
                            stream.write(b",")
                            size += 1
                        stream.write(data)
                        size += len(data)
                        count, total = count+1, total+1
                    if stream is None:
                        stream = private_open(directory / f"{table}-{index:06}.json")
                        stream.write(b"[")
                    stream.write(b"]")
                    records[f"state/{table}-{index:06}.json"] = count
                finally:
                    if stream:
                        stream.close()
        return records

    def pack(self, folder, boundary, destination):
        records = self.export_state(folder / "snapshot.sqlite3", folder / "state")
        inventory = folder / "inventory.json"
        with private_open(inventory) as out:
            out.write(b'{"format":"mastermind-backup/v1","members":[')
            count, total = 0, 0
            for root in ("vault", "state"):
                for relative, path in file_inventory(folder / root):
                    relative = root + "/" + relative
                    item = {"path": relative, "sha256": sha_file(path), "size": path.stat().st_size,
                            "records": records.get(relative), "mode": path.stat().st_mode & 0o777,
                            "mtime_ns": path.stat().st_mtime_ns}
                    total += item["size"]
                    count += 1
                    if total > self.config.max_expanded_bytes or count + 1 > self.config.max_archive_entries:
                        raise DomainError("SIZE_LIMIT", "The backup inventory exceeds its limit.", 413)
                    if count > 1:
                        out.write(b",")
                    out.write(canonical(item))
            out.write(b'],"directories":[')
            directory_count = 0
            for relative, _ in directory_inventory(folder / "vault"):
                if directory_count:
                    out.write(b",")
                directory = folder / "vault" / relative
                out.write(canonical({"path": "vault/" + relative, "mode": directory.stat().st_mode & 0o777}))
                directory_count += 1
                if directory_count + count + 1 > self.config.max_archive_entries:
                    raise DomainError("SIZE_LIMIT", "The backup tree exceeds its entry limit.", 413)
            out.write(b"]}")
        inner, encrypted = folder / "logical.zip", folder / "payload.age"
        # Stored ZIP members avoid excessive compression ratios for opaque plugin data.
        with private_open(inner) as raw, zipfile.ZipFile(raw, "w", zipfile.ZIP_STORED) as archive:
            self.zip_file(archive, inventory, "inventory.json")
            for root in ("vault", "state"):
                for relative, path in file_inventory(folder / root):
                    self.zip_file(archive, path, root + "/" + relative)
        recipient_text = self.secrets.read("recovery_recipient")
        transform("encrypt", inner, encrypted, self.secrets, self.config.max_backup_bytes)
        unsigned = {"format": FORMAT, "service_version": __version__, "schema": 1, **boundary,
                    "payload": {"size": encrypted.stat().st_size, "sha256": sha_file(encrypted)},
                    "encryption": "age/X25519", "key_id": hashlib.sha256(recipient_text.encode()).hexdigest(),
                    "inventory_sha256": sha_file(inventory), "member_count": count,
                    "directory_count": directory_count,
                    "expanded_bytes": total, "limits": {"compressed": self.config.max_backup_bytes,
                    "expanded": self.config.max_expanded_bytes, "members": self.config.max_archive_entries}}
        signature = base64.b64encode(self.signing_key().sign(canonical(unsigned))).decode("ascii")
        manifest = {"manifest": unsigned, "signature": signature}
        with private_open(destination) as raw, zipfile.ZipFile(raw, "w", zipfile.ZIP_STORED) as archive:
            archive.writestr("manifest.json", canonical(manifest))
            self.zip_file(archive, encrypted, "payload.age")
            raw.flush()
            os.fsync(raw.fileno())
        if destination.stat().st_size > self.config.max_backup_bytes:
            destination.unlink()
            raise DomainError("SIZE_LIMIT", "The complete backup exceeds its limit.", 413)
        # Check the completed ciphertext and its external trust before offering it.
        self.verify_wrapper(destination)
        return unsigned

    def zip_file(self, archive, path, name):
        # ZipFile.write uses an uninterruptible copy loop. Keep ZIP metadata but
        # check the enclosing preparation budget between bounded file chunks.
        info = zipfile.ZipInfo.from_file(path, name)
        with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
            copy_bounded(source, target, self.config.max_expanded_bytes)

    def create(self, destination, *, inside_boundary=False):
        destination = Path(destination)
        self.trust_key()
        self.signing_key()
        self.secrets.read("recovery_recipient")
        with self.spool.operation(self.estimate() * 5) as folder:
            boundary = self.snapshot(folder, inside_boundary=inside_boundary)
            output = folder / "output.zip"
            result = self.pack(folder, boundary, output)
            with private_open(destination) as dst:
                try:
                    with output.open("rb") as src:
                        copy_bounded(src, dst, self.config.max_backup_bytes)
                except BaseException:
                    dst.close()
                    destination.unlink(missing_ok=True)
                    raise
        self.audit.emit("backup.create", target="full_archive",
                        context={"generation": result["generation"], "bytes": destination.stat().st_size})
        return result

    def verify_wrapper(self, source):
        if source.stat().st_size > self.config.max_backup_bytes:
            raise DomainError("INVALID_ARCHIVE", "Backup exceeds the compressed size limit.", 413)
        try:
            with zipfile.ZipFile(source) as archive:
                members = zip_members(archive, self.config, outer=True)
                if members["manifest.json"].file_size > 64*1024:
                    raise DomainError("INVALID_ARCHIVE", "Backup manifest is too large.", 422)
                envelope = checked_json(archive.read("manifest.json"))
                unsigned = envelope["manifest"]
                self.trust_key().verify(base64.b64decode(envelope["signature"], validate=True), canonical(unsigned))
                if unsigned["format"] != FORMAT or unsigned["schema"] != 1 \
                        or unsigned["encryption"] != "age/X25519":
                    raise DomainError("INCOMPATIBLE_BACKUP", "Backup format or schema is not supported.", 422)
                if members["payload.age"].file_size != unsigned["payload"]["size"]:
                    raise DomainError("INVALID_ARCHIVE", "Ciphertext size does not match its manifest.", 422)
                with archive.open("payload.age") as stream:
                    digest = stream_digest(stream)
                if digest != unsigned["payload"]["sha256"]:
                    raise DomainError("INVALID_ARCHIVE", "Ciphertext digest does not match its manifest.", 422)
                if not 0 <= unsigned["expanded_bytes"] <= self.config.max_expanded_bytes \
                        or not 0 <= unsigned["member_count"] < self.config.max_archive_entries:
                    raise DomainError("INVALID_ARCHIVE", "Inventory bounds exceed this recovery profile.", 413)
                return unsigned
        except (ValueError, KeyError, TypeError, InvalidSignature, zipfile.BadZipFile):
            raise DomainError("INVALID_ARCHIVE", "Backup signature, format or integrity check failed.", 422) from None

    def unpack(self, source, folder):
        """Return a completely checked private generation. Never writes live Vault/state."""
        manifest = self.verify_wrapper(source)
        encrypted, inner = folder / "payload.age", folder / "logical.zip"
        with zipfile.ZipFile(source) as outer, outer.open("payload.age") as src, private_open(encrypted) as dst:
            copy_bounded(src, dst, self.config.max_backup_bytes)
        transform("decrypt", encrypted, inner, self.secrets, self.config.max_expanded_bytes)
        tree = folder / "checked"
        tree.mkdir(mode=0o700)
        (tree / "vault").mkdir(mode=0o700)
        try:
            with zipfile.ZipFile(inner) as archive:
                members = zip_members(archive, self.config)
                if "inventory.json" not in members or members["inventory.json"].file_size > 64*1024**2:
                    raise DomainError("INVALID_ARCHIVE", "A bounded inventory is required.", 422)
                with archive.open("inventory.json") as src:
                    if hashlib.file_digest(src, "sha256").hexdigest() != manifest["inventory_sha256"]:
                        raise DomainError("INVALID_ARCHIVE", "Protected inventory integrity failed.", 422)
                seen, counts, total = set(), {}, 0
                with archive.open("inventory.json") as stream:
                    for item in ijson.items(stream, "members.item", use_float=True):
                        path = safe_relative(item["path"])
                        part = PART.fullmatch(path)
                        if path in seen or path not in members or not (path.startswith("vault/") or part):
                            raise DomainError("INVALID_ARCHIVE", "Inventory contains an unexpected member.", 422)
                        if part and (part[1] not in MANDATORY_TABLES or item["size"] > STATE_PART_BYTES):
                            raise DomainError("INVALID_ARCHIVE", "State part is unsupported or oversized.", 422)
                        if members[path].file_size != item["size"]:
                            raise DomainError("INVALID_ARCHIVE", "Inventory size mismatch.", 422)
                        seen.add(path)
                        total += item["size"]
                        destination = resolve(tree, path, internal=True)
                        with archive.open(path) as src, private_open(destination) as dst:
                            size, digest = copy_bounded(src, dst, item["size"])
                        if digest != item["sha256"] or size != item["size"]:
                            raise DomainError("INVALID_ARCHIVE", "Member integrity check failed.", 422)
                        mode, modified = item.get("mode", 0o600), item.get("mtime_ns", 0)
                        if type(mode) is not int or not 0 <= mode <= 0o777 or type(modified) is not int \
                                or not 0 <= modified <= 32503680000*10**9:
                            raise DomainError("INVALID_ARCHIVE", "Member file metadata is invalid.", 422)
                        if os.name == "posix":
                            os.chmod(destination, mode)
                        if modified:
                            os.utime(destination, ns=(modified, modified))
                        if part:
                            counts[path] = item["records"]
                if seen != set(members) - {"inventory.json"} or len(seen) != manifest["member_count"] \
                        or total != manifest["expanded_bytes"]:
                    raise DomainError("INVALID_ARCHIVE", "Inventory coverage is incomplete.", 422)
                dirs, normalized_files = set(), {name_key(path) for path in seen}
                directory_modes = []
                with archive.open("inventory.json") as stream:
                    for directory in ijson.items(stream, "directories.item"):
                        path = directory if isinstance(directory, str) else directory["path"]
                        mode = 0o700 if isinstance(directory, str) else directory.get("mode", 0o700)
                        if type(mode) is not int or not 0 <= mode <= 0o777:
                            raise DomainError("INVALID_ARCHIVE", "Directory file metadata is invalid.", 422)
                        safe_relative(path)
                        key = name_key(path)
                        if not path.startswith("vault/") or key in dirs or key in normalized_files \
                                or len(dirs) + len(seen) + 1 >= self.config.max_archive_entries:
                            raise DomainError("INVALID_ARCHIVE", "Directory inventory is invalid.", 422)
                        dirs.add(key)
                        destination = resolve(tree, path, internal=True)
                        destination.mkdir(mode=0o700, parents=True, exist_ok=True)
                        directory_modes.append((destination, mode))
                if os.name == "posix":
                    for destination, mode in reversed(directory_modes):
                        os.chmod(destination, mode)
                if len(dirs) != manifest.get("directory_count", 0):
                    raise DomainError("INVALID_ARCHIVE", "Directory inventory count is invalid.", 422)
                self.import_state(tree, counts)
        except (ValueError, TypeError, KeyError, sqlite3.Error, zipfile.BadZipFile, ijson.JSONError):
            raise DomainError("INVALID_ARCHIVE", "Logical backup validation failed.", 422) from None
        return tree, manifest

    def import_state(self, tree, counts):
        tables = {table: [] for table in MANDATORY_TABLES}
        for path in counts:
            tables[PART.fullmatch(path)[1]].append(path)
        restored = State(tree / "restored.sqlite3")
        try:
            with restored.transaction() as db:
                for table, parts in tables.items():
                    if not parts:
                        raise DomainError("INVALID_ARCHIVE", "A mandatory state table is missing.", 422)
                    db.execute(f'DELETE FROM "{table}"')
                    columns = [r[1] for r in db.execute(f'PRAGMA table_info("{table}")')]
                    sql = f'INSERT INTO "{table}" VALUES({",".join("?" for _ in columns)})'
                    for index, path in enumerate(sorted(parts)):
                        if int(PART.fullmatch(path)[2]) != index:
                            raise DomainError("INVALID_ARCHIVE", "State parts are not contiguous.", 422)
                        count = 0
                        # Each part is capped at 4 MiB, including before JSON parsing.
                        rows = checked_json((tree / path).read_bytes())
                        if not isinstance(rows, list):
                            raise DomainError("INVALID_ARCHIVE", "State part must contain records.", 422)
                        for row in rows:
                            if not isinstance(row, dict) or set(row) != set(columns) \
                                    or len(canonical(row)) > STATE_RECORD_BYTES:
                                raise DomainError("INVALID_ARCHIVE", "State record schema is incompatible.", 422)
                            db.execute(sql, [row[c] for c in columns])
                            count += 1
                        if count != counts[path]:
                            raise DomainError("INVALID_ARCHIVE", "State record count does not match inventory.", 422)
                if restored.one("SELECT value FROM metadata WHERE key='schema'") != {"value": "1"}:
                    raise DomainError("INCOMPATIBLE_BACKUP", "State schema is not supported.", 422)
                for row in restored.rows("SELECT path FROM shares UNION SELECT path FROM activity"):
                    safe_relative(row["path"])
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise DomainError("INVALID_ARCHIVE", "Restored database failed integrity.", 422)
        finally:
            restored.close()

    def inspect(self, source):
        source = Path(source)
        manifest = self.verify_wrapper(source)
        with self.spool.operation(manifest["expanded_bytes"]*3 + source.stat().st_size*2 + 64*1024**2) as folder:
            tree, _ = self.unpack(source, folder)
            names = set()
            notes = 0
            for relative, path in file_inventory(tree / "vault"):
                if relative.lower().endswith(".md") and not any(p.startswith(".") for p in relative.split("/")):
                    key = name_key(path.stem)
                    if key in names:
                        raise DomainError("DUPLICATE_BASENAME", "Backup contains conflicting note names.", 422)
                    names.add(key)
                    notes += 1
            with closing(sqlite3.connect(tree / "restored.sqlite3")) as db:
                counts = {table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                          for table in MANDATORY_TABLES}
            return {"manifest": manifest, "notes": notes, "state_records": counts,
                    "sessions_will_be_invalidated": True, "current_state_will_be_replaced": True}

    def mirror(self, destination):
        with self.spool.operation(self.estimate()*3) as folder:
            boundary = self.snapshot(folder)
            with private_open(destination) as raw, zipfile.ZipFile(raw, "w", zipfile.ZIP_STORED) as archive:
                for relative, path in directory_inventory(folder / "vault"):
                    archive.write(path, relative + "/")
                for relative, path in file_inventory(folder / "vault"):
                    archive.write(path, relative)
            if destination.stat().st_size > self.config.max_backup_bytes:
                destination.unlink()
                raise DomainError("SIZE_LIMIT", "Mirror exceeds its export limit.", 413)
            return {**boundary, "sha256": sha_file(destination), "bytes": destination.stat().st_size}
