import os
import threading
import time

import psutil

from mastermind.fs import sha_file


def test_356_mib_backup_stream_and_clean_restore(recovery, tmp_path, record_property):
    backup, restore, auth = recovery
    auth.initialize("representative-test")
    backup.vault.write("root.md", "#main\nLarge archive qualification", None, create=True)
    source = backup.config.vault / "representative.bin"
    with source.open("wb") as stream:
        for _ in range(356):
            stream.write(os.urandom(1024**2))
    expected = sha_file(source)
    process = psutil.Process()
    baseline = process.memory_info().rss
    peak = baseline
    stop = threading.Event()
    def monitor():
        nonlocal peak
        while not stop.wait(0.02):
            try:
                total = process.memory_info().rss
                for child in process.children(recursive=True):
                    try:
                        total += child.memory_info().rss
                    except psutil.NoSuchProcess:
                        pass
                peak = max(peak, total)
            except psutil.NoSuchProcess:
                return
    watcher = threading.Thread(target=monitor)
    watcher.start()
    try:
        started = time.monotonic()
        archive = tmp_path / "large.zip"
        backup.create(archive)
        record_property("backup_seconds", time.monotonic() - started)
        assert archive.stat().st_size > 350*1024**2
        source.unlink()
        started = time.monotonic()
        restore.apply(archive)
        record_property("restore_seconds", time.monotonic() - started)
        assert time.monotonic() - started < 15*60
        assert sha_file(source) == expected
    finally:
        stop.set()
        watcher.join()
    record_property("extra_parent_and_crypto_process_rss_bytes", peak-baseline)
    assert peak-baseline <= 128*1024**2
    assert not list(backup.spool.directory.iterdir())
