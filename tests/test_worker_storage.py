import json
import os
import time

import pytest

from mastermind.errors import DomainError
from mastermind.fs import atomic_json, sha_bytes
from mastermind.worker import Worker


@pytest.fixture
def worker(tmp_path):
    instance = Worker(tmp_path / "work", tmp_path / "model", tmp_path / "inventory", tmp_path / "credential")
    identifier = "a"*32
    folder = instance.reserve(identifier, 12)
    instance.active = None
    (folder / "source").write_bytes(b"source bytes")
    atomic_json(folder / "source.json", {"size": 12, "sha256": sha_bytes(b"source bytes"), "mime": "text/plain", "name": "source.txt"})
    return instance, identifier, folder


@pytest.mark.parametrize("mutation", ["large", "list", "size", "digest", "header"])
def test_parser_writable_metadata_is_bounded_and_validated(worker, mutation):
    instance, identifier, folder = worker
    metadata = json.loads((folder / "source.json").read_bytes())
    if mutation == "large":
        metadata["extra"] = "a"*20000
    elif mutation == "list":
        metadata = []
    elif mutation == "size":
        metadata["size"] = 2*1024**3+1
    elif mutation == "digest":
        (folder / "source").write_bytes(b"tampered")
    elif mutation == "header":
        metadata["mime"] = "text/plain\r\nX-Injected: value"
    (folder / "source.json").write_text(json.dumps(metadata))
    with pytest.raises(DomainError) as failure:
        instance.source(identifier)
    assert failure.value.code == "SOURCE_UNAVAILABLE"


@pytest.mark.skipif(os.name == "nt", reason="Real Linux qualification covers filesystem link boundaries")
@pytest.mark.parametrize("name", ["source", "source.json"])
def test_parent_never_follows_a_parser_created_link(worker, tmp_path, name):
    instance, identifier, folder = worker
    outside = tmp_path / "private-canary"
    outside.write_bytes((folder / name).read_bytes())
    (folder / name).unlink()
    (folder / name).symlink_to(outside)
    with pytest.raises(DomainError) as failure:
        instance.source(identifier)
    assert failure.value.code == "SOURCE_UNAVAILABLE"


def test_cleanup_retains_active_streams_and_releases_only_expired_private_work(worker):
    instance, identifier, folder = worker
    os.utime(folder, (time.time()-90000, time.time()-90000))
    instance.readers[identifier] = 1
    instance.cleanup_expired()
    assert folder.exists()
    with pytest.raises(DomainError):
        instance.cleanup(identifier)
    instance.readers.clear()
    instance.active = identifier
    instance.cleanup_expired()
    assert folder.exists()
    instance.active = None
    instance.cleanup_expired()
    assert not folder.exists()
