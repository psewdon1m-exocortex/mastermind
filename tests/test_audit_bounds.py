import json
import time
import zipfile


def test_audit_count_age_and_byte_retention(recovery):
    backup, _, _ = recovery
    now = time.time()
    with backup.state.transaction() as db:
        db.executemany("INSERT INTO audit(id,occurred_at,bytes,event) VALUES(?,?,?,?)",
                       [(f"event-{i}", now, 100, json.dumps({"id": f"event-{i}"})) for i in range(10010)])
        db.execute("INSERT INTO audit(id,occurred_at,bytes,event) VALUES('expired',?,100,'{}')",
                   (now - 31*86400,))
    backup.audit.emit("test.retention")
    assert backup.state.one("SELECT COUNT(*) AS count FROM audit")["count"] == 10000
    assert backup.state.one("SELECT * FROM audit WHERE id='expired'") is None
    with backup.state.transaction() as db:
        db.execute("UPDATE audit SET bytes=10000")
    backup.audit.emit("test.byte_retention")
    assert backup.state.one("SELECT SUM(bytes) AS size FROM audit")["size"] <= 64*1024**2
    assert len(backup.audit.page(0, 100000)) == 1000


def test_file_log_rotation_bounds_each_file(recovery):
    backup, _, _ = recovery
    line = (b"x" * 16000) + b"\n"
    for _ in range(400):
        backup.audit.append(line)
    files = list(backup.audit.directory.glob("*.jsonl"))
    assert len(files) == 2
    assert all(path.stat().st_size <= 5*1024**2 for path in files)


def test_log_export_has_one_bounded_snapshot_during_concurrent_append(recovery, tmp_path, monkeypatch):
    backup, _, _ = recovery
    audit = backup.audit
    early = audit.emit("early", outcome="error", error={"code": "TEST"})
    original = audit._export_snapshot
    def concurrent(destination, page, boundary):
        audit.emit("late", outcome="error", error={"code": "AFTER_BOUNDARY"})
        return original(destination, page, boundary)
    monkeypatch.setattr(audit, "_export_snapshot", concurrent)
    destination = tmp_path / "logs.zip"
    audit.export(destination)
    with zipfile.ZipFile(destination) as archive:
        events = [json.loads(line) for line in archive.read("events.jsonl").splitlines()]
        errors = json.loads(archive.read("errors.json"))
        manifest = json.loads(archive.read("manifest.json"))
    assert {event["action"] for event in events} == {"early", "audit.export"}
    assert [event["id"] for event in errors] == [early]
    assert max(event["sequence"] for event in events) == manifest["boundary_sequence"]
    assert audit.page(None, 1)[0]["action"] == "late"
