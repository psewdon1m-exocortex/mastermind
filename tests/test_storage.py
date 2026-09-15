import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from mastermind.coordinator import Coordinator
from mastermind.errors import DomainError
from mastermind.fs import resolve, sha_file
from mastermind.references import note_tags, parse


def test_real_files_fts_graph_and_history(service):
    config, state, _, vault = service
    vault.write("root.md", "#main\n[[Topic]] @Topic", None, create=True)
    vault.write("Branch/Topic.md", "A meaningful search term.", None, create=True)
    assert vault.list("meaningful")[0]["path"] == "Branch/Topic.md"
    assert vault.graph()["connectedness"] == 100
    assert len(vault.graph()["edges"]) == 1
    target_sha = sha_file(config.vault / "Branch/Topic.md")
    vault.delete("Branch/Topic.md", target_sha)
    vault.index(force=True)
    assert vault.graph()["broken"] == 1
    assert state.one("SELECT display FROM reference_history WHERE name_key='topic'")["display"] == "Topic"
    vault.write("Elsewhere/Topic.md", "new", None, create=True)
    assert vault.graph()["broken"] == 0


@pytest.mark.parametrize("left,right", [
    ("A/Example.md", "B/example.md"), ("Straße.md", "STRASSE.md"),
    ("Café.md", "Cafe\u0301.md")
])
def test_global_casefold_nfc_collisions(service, left, right):
    _, _, _, vault = service
    vault.write(left, "first", None, create=True)
    with pytest.raises(DomainError) as error:
        vault.write(right, "second", None, create=True)
    assert error.value.code == "DUPLICATE_BASENAME"
    assert vault.read(left) == "first"
    assert len(vault.files()) == 1


@pytest.mark.parametrize("relative", [
    "../note.md", "/tmp/note.md", r"C:\note.md", "a//b.md", "a/./b.md",
    "a/../b.md", "a\0.md", ".obsidian/private.md", "CON.md", "name .md/..",
])
def test_paths_reject_unsafe_or_private(service, relative):
    config, _, _, _ = service
    with pytest.raises(DomainError):
        resolve(config.vault, relative)


def test_hardlink_rejected(service):
    config, _, _, vault = service
    vault.write("A.md", "data", None, create=True)
    os.link(config.vault / "A.md", config.vault / "B.md")
    with pytest.raises(DomainError, match="Hard-linked"):
        vault.inventory()


def test_two_concurrent_expected_hash_writes_one_wins(service):
    _, _, _, vault = service
    initial = vault.write("A.md", "before", None, create=True)["sha256"]
    def save(text):
        try:
            vault.write("A.md", text, initial)
            return "ok"
        except DomainError as error:
            return error.code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(save, ["first", "second"]))
    assert sorted(results) == ["CONFLICT", "ok"]
    assert vault.read("A.md") in ("first", "second")


class Crash(BaseException):
    pass


@pytest.mark.parametrize("point,expected", [
    ("prepared", ("old A", "old B")), ("file:0", ("old A", "old B")),
    ("file:1", ("new A", "new B")), ("committed", ("new A", "new B")),
])
def test_crash_at_every_write_boundary_recovers_whole_batch(service, point, expected):
    config, state, coordinator, vault = service
    vault.write("A.md", "old A", None, create=True)
    vault.write("B.md", "old B", None, create=True)
    hashes = {p: sha_file(config.vault / p) for p in ("A.md", "B.md")}
    def fail(stage):
        if stage == point:
            raise Crash()
    coordinator.fault = fail
    with pytest.raises(Crash):
        coordinator.commit({"A.md": b"new A", "B.md": b"new B"}, hashes)
    recovered = Coordinator(config, state, coordinator.runtime)
    recovered.recover()
    assert (vault.read("A.md"), vault.read("B.md")) == expected
    assert not list(recovered.directory.iterdir())
    recovered.recover()
    assert (vault.read("A.md"), vault.read("B.md")) == expected


def test_recovery_never_overwrites_unknown_writer(service):
    config, state, coordinator, vault = service
    vault.write("A.md", "before", None, create=True)
    def fail(stage):
        if stage == "file:0":
            raise Crash()
    coordinator.fault = fail
    with pytest.raises(Crash):
        coordinator.commit({"A.md": b"ours", "B.md": b"next"},
                           {"A.md": sha_file(config.vault / "A.md"), "B.md": None})
    (config.vault / "A.md").write_text("somebody else's saved edit", "utf-8")
    with pytest.raises(DomainError, match="unknown writer"):
        Coordinator(config, state, coordinator.runtime).recover()
    assert vault.read("A.md") == "somebody else's saved edit"


def test_markdown_parser_exclusions_and_longest_match():
    dictionary = {"example": "Example", "example note": "Example note", "café": "Café",
                  "strasse": "Straße"}
    text = "---\ntags: [main]\nx: '@Example'\n---\n@Example note. @Examplemore user@Example.org\n"
    text += "\\@Example \u0060@Example\u0060\n\u0060\u0060\u0060md\n@Example\n\u0060\u0060\u0060\n"
    text += "<!-- @Example -->\n@Cafe\u0301 @STRASSE [[Example|label]]"
    refs = parse(text, dictionary)
    assert [r.target for r in refs] == ["example note", "café", "strasse", "example"]
    assert text[refs[1].start:refs[1].end] == "@Cafe\u0301"
    assert note_tags(text) == ["main"]


def test_deleted_name_history_and_namespaces():
    refs = parse("@Old name @chronos: event-123 @unknown: text @saturn: root/my file.pdf",
                 {}, ["Old name"], ["root/my file.pdf"])
    assert [(r.kind, r.target, r.exists) for r in refs] == [
        ("internal", "old name", False), ("chronos", "event-123", True),
        ("saturn", "root/my file.pdf", True)
    ]


def test_dictionary_change_invalidates_untouched_source(service):
    _, _, _, vault = service
    vault.write("Example.md", "one", None, create=True)
    vault.write("Source.md", "@Example note", None, create=True)
    assert ["Example.md", "Source.md"] in vault.graph()["edges"]
    vault.write("Example note.md", "two", None, create=True)
    assert ["Example note.md", "Source.md"] in vault.graph()["edges"]
    assert ["Example.md", "Source.md"] not in vault.graph()["edges"]
