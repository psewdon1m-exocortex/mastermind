"""Portable Obsidian copies contain Vault bytes and only Bridge-owned metadata."""
import sqlite3
import zipfile
from contextlib import closing

from . import __version__
from .backup import canonical
from .errors import DomainError
from .fs import directory_inventory, file_inventory, sha_file
from .spool import private_open

PREFIX = ".obsidian/plugins/mastermind-bridge/"
HISTORY = PREFIX + "portable-history.json"
MANIFEST = PREFIX + "portable-export.json"


def pack(folder, boundary, destination, config):
    tree = folder / "vault"
    # The running Runtime installs the bundled Bridge before a snapshot is allowed.
    for name in ("main.js", "manifest.json", "styles.css"):
        if not (tree / PREFIX / name).is_file():
            raise DomainError("BRIDGE_UNAVAILABLE", "The Vault needs its bundled Bridge before portable export.", 503)
    history = {"format": "mastermind-portable-history/v1", "internal": [], "saturn": []}
    history_bytes = 0
    with closing(sqlite3.connect(folder / "snapshot.sqlite3")) as db:
        for kind, display in db.execute("SELECT kind,display FROM reference_history WHERE kind IN ('internal','saturn') "
                                        "ORDER BY kind,name_key"):
            history_bytes += len(canonical(display)) + 1
            if len(display) > 1024 or len(history[kind]) >= 100_000 or history_bytes > 16*1024**2-1024:
                raise DomainError("SIZE_LIMIT", "The portable history snapshot exceeds its limit.", 413)
            history[kind].append(display)
    history_data = canonical(history)
    manifest_path = folder / "portable-export.json"
    additions = [HISTORY, MANIFEST]
    with private_open(manifest_path) as manifest:
        header = {"format": "mastermind-portable-export/v1", "service_version": __version__, **boundary,
                  "mode": "standalone-copy", "sync_supported": False,
                  "generated_files": additions,
                  "replaced_bridge_metadata": [path for path in additions if (tree / path).exists()]}
        manifest.write(canonical(header)[:-1] + b',"original_files":[')
        count, total = 0, 0
        for relative, path in file_inventory(tree):
            if relative in additions:
                continue
            total += path.stat().st_size
            if total > config.max_expanded_bytes or count + 2 >= config.max_archive_entries:
                raise DomainError("SIZE_LIMIT", "The portable inventory exceeds its limit.", 413)
            if count:
                manifest.write(b",")
            manifest.write(canonical({"path": relative, "sha256": sha_file(path), "size": path.stat().st_size}))
            count += 1
        manifest.write(b"]}")
    with private_open(destination) as raw, zipfile.ZipFile(raw, "w", zipfile.ZIP_STORED) as archive:
        for relative, path in directory_inventory(tree):
            archive.write(path, relative + "/")
        for relative, path in file_inventory(tree):
            if relative not in additions:
                archive.write(path, relative)
        archive.writestr(HISTORY, history_data)
        archive.write(manifest_path, MANIFEST)
    if destination.stat().st_size > config.max_backup_bytes:
        destination.unlink()
        raise DomainError("SIZE_LIMIT", "The portable export exceeds its limit.", 413)
