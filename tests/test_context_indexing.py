import json
import time
from types import SimpleNamespace

import pytest

from mastermind.audit import Audit
from mastermind.context_indexing import ContextIndexing
from mastermind.context_indexing.graph import Graph, Scope
from mastermind.context_indexing.index import Index
from mastermind.context_indexing.pipeline import Pipeline, source_features
from mastermind.context_indexing.policy import PlacementPolicy
from mastermind.context_indexing.settings import Settings
from mastermind.context_indexing.template import DEFAULT_PATH, DEFAULT_TEMPLATE, parse, render
from mastermind.errors import DomainError
from mastermind.fs import sha_bytes


@pytest.fixture
def context(service):
    config, state, coordinator, vault = service
    return SimpleNamespace(config=config, state=state, coordinator=coordinator, vault=vault,
                           audit=Audit(config, state), data_ready=lambda: None)


def seed(context):
    notes = {"root.md": "[[Science]]\n[[Arts]]", "Topics/Science.md": "#main\n[[Algebra]]",
             "Topics/Algebra.md": "#key\nMathematical algebra equations.", "Topics/Arts.md": "#main\nPainting pictures.",
             "Notes/Ordinary.md": "Polynomials factorization algebra equations.\n[[Algebra]]",
             "Notes/Unlinked.md": "Nebula interstellar astronomy."}
    for path, body in notes.items():
        context.vault.write(path, body, None, create=True)
    return notes


def test_scoped_profiles_do_not_replace_or_delete_global_profiles(context):
    seed(context)
    settings = Settings(context)
    settings.bootstrap()
    index = Index(context)
    full = Graph(context.vault, Scope("owner"))
    index.profiles(full, full.structure(), settings.get())
    before = context.state.rows("SELECT * FROM context_profiles ORDER BY path")
    limited = Graph(context.vault, Scope("owner", frozenset({"root.md", "Topics/Science.md", "Topics/Algebra.md"})))
    index.profiles(limited, limited.structure(), settings.get())
    assert context.state.rows("SELECT * FROM context_profiles ORDER BY path") == before


def test_idle_maintenance_expires_traces_without_query_or_graph_changes(context):
    settings = Settings(context)
    with context.state.transaction() as db:
        db.execute("INSERT INTO context_traces VALUES(?,?,?,?)", ("expired", time.time()-8*86400, 2, "{}"))
        db.execute("INSERT INTO context_traces VALUES(?,?,?,?)", ("recent", time.time(), 2, "{}"))
    engine = object.__new__(ContextIndexing)
    engine.next_batch, engine.service, engine.settings, engine.index = 0, context, settings, Index(context)
    engine.completed_batch = (context.state.one("SELECT value FROM metadata WHERE key='generation'")["value"],
        0, context.state.setting("semantic_model_sha"), settings.get()["revision"])
    engine.maintain()
    assert context.state.rows("SELECT id FROM context_traces") == [{"id": "recent"}]


def test_scoped_profile_search_cannot_use_private_member_terms(context):
    seed(context)
    context.vault.write("Private.md", "UNIQUEPRIVATEWORD\n[[Algebra]]", None, create=True)
    settings = Settings(context)
    settings.bootstrap()
    index = Index(context)
    full = Graph(context.vault, Scope("owner"))
    index.profiles(full, full.structure(), settings.get())
    scope = Scope("owner", frozenset({"root.md", "Topics/Science.md", "Topics/Algebra.md"}))
    result, _ = Pipeline(context, index).run({"text": "UNIQUEPRIVATEWORD"}, scope=scope,
        query_type="placement_analysis", configuration=settings.get())
    assert not result["results"]


def test_long_source_sampling_covers_both_ends_without_disabling_placement():
    raw = "FIRST SECTION " + "material "*10000 + " FINAL SECTION"
    features = source_features({"title": "Topic", "summary": "Summary"}, raw)
    assert len(features["raw_chunks"]) == 8
    assert features["raw_chunks"][0].startswith("FIRST SECTION")
    assert features["raw_chunks"][-1].endswith("FINAL SECTION")
    assert features["source_sampled"] and not features["truncated"]


def test_counterevidence_does_not_invoke_curator(context):
    seed(context)
    settings = Settings(context)
    settings.bootstrap()

    class ForbiddenCurator:
        def refine(self, *args, **kwargs):
            pytest.fail("Counterevidence must not be reinterpreted by Curator")

    result, _ = Pipeline(context, Index(context), curator=ForbiddenCurator()).run(
        {"text": "Algebra equations"}, configuration={**settings.get(), "curator_enabled": True},
        assessment=lambda *_: {"status": "ambiguous", "reason": "SOURCE_TOPIC_CONFLICT", "refinement_may_help": False})
    assert not result["curator"]["invoked"]


def test_calibration_cannot_mix_embedding_model_versions(context):
    settings = Settings(context)
    policy = PlacementPolicy(settings, calibration={"qualified": True, "policy_version": "crusher.placement.v1",
        "version": "fixture", "embedding_sha256": "qualified-model", "variants": {
            "complete": {"score": .8, "gap": .1, "lexical": .2},
            "vector": {"score": .3, "gap": .1, "lexical": .2}}})
    context.state.set_setting("semantic_model_sha", "different-model")
    assert policy.thresholds({"missing_strategies": []}) is None
    assert policy.thresholds({"missing_strategies": ["vector"]})["variant"] == "vector"


def test_calibration_cannot_mix_search_representations(context):
    settings = Settings(context)
    policy = PlacementPolicy(settings, calibration={'qualified': True, 'policy_version': 'crusher.placement.v1',
        'version': 'fixture', 'variants': {'complete': {'score': .8, 'gap': .1}}})
    context.state.set_setting('semantic_representation', 'search-content.v1')
    assert policy.thresholds({'missing_strategies': []}) is None
    policy.calibration['search_representation'] = 'search-content.v1'
    assert policy.thresholds({'missing_strategies': []}) is not None


def test_explicit_topic_exclusion_rejects_even_high_scoring_technical_anchor(context):
    seed(context)
    settings = Settings(context)
    settings.bootstrap()
    policy = PlacementPolicy(settings, calibration={"qualified": True, "policy_version": "crusher.placement.v1",
        "version": "fixture", "variants": {"complete": {"score": .1, "gap": 0, "lexical": 0}}})
    graph = Graph(context.vault, Scope("crusher"))
    evidence = {"path": "Topics/Algebra.md", "sha256": graph.notes["Topics/Algebra.md"]["sha"],
                "score": .99, "features": {"lexical": 1, "title_match": 1}}
    result = {"results": [evidence], "missing_strategies": [], "truncated": False}
    assert policy.assess(result, graph)["status"] == "sufficient"
    subject = source_features({"title": "Craft", "summary": "Paper folding"},
        "A craft unrelated to mathematical problem solving.")
    assert subject["topic_exclusions"]
    assessment = policy.assess({**result, "topic_exclusions": subject["topic_exclusions"]}, graph)
    assert assessment["status"] == "ambiguous" and assessment["reason"] == "SOURCE_COUNTEREVIDENCE"
    assert not assessment["refinement_may_help"]


def test_backup_roundtrip_retains_configuration_templates_and_output(recovery, tmp_path):
    backup, restore, _auth = recovery
    service = SimpleNamespace(state=backup.state, vault=backup.vault, coordinator=backup.coordinator,
                              audit=backup.audit, config=backup.config)
    seed(service)
    settings = Settings(service)
    settings.bootstrap()
    before = settings.change({"curator_enabled": True, "expected_revision": settings.get()["revision"],
                              "operation_id": "backup-curator-configuration"})
    backup.vault.write("root/crusher/Archived.md", "Stored result\n[[pool]]", None, create=True)
    archive = tmp_path/"context-roundtrip.zip"
    backup.create(archive)
    settings.change({"curator_enabled": False, "expected_revision": before["revision"],
                     "operation_id": "mutate-before-restore-01"})
    assert restore.apply(archive)["state"] == "COMPLETED"
    assert settings.get() == before
    assert settings.snapshot()["template"]["text"] == DEFAULT_TEMPLATE
    assert backup.vault.read("root/crusher/Archived.md") == "Stored result\n[[pool]]"
    assert backup.state.one("SELECT value FROM metadata WHERE key='schema'")["value"] == "2"


def test_template_deterministic_snapshot_and_nonrecursive_substitution():
    template = parse(DEFAULT_TEMPLATE)
    fields = {"title": "A [title]", "summary": "Summary", "body": "Literal {{crusher.links}} from source"}
    first = render(template, fields, sources="text source", link="[[pool]]", timestamp=100, timezone="UTC")
    assert first == render(template, fields, sources="text source", link="[[pool]]", timestamp=100)
    assert first.count("[[pool]]") == 1 and "Literal {{crusher.links}}" in first
    assert "# A \\[title\\]" in first
    with pytest.raises(DomainError):
        render({**template, "text": template["text"]+"changed"}, fields, sources="", link="", timestamp=100)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_template_frontmatter_cannot_bypass_validation_with_line_endings(newline):
    valid = ("---\ncategory: science\n...\n" + DEFAULT_TEMPLATE).replace("\n", newline)
    assert parse(valid)["text"] == valid
    for metadata in ["category: &a science\ncopy: *a", "url: https://private.invalid", "tags: [key]"]:
        with pytest.raises(DomainError):
            parse(("---\n"+metadata+"\n---\n"+DEFAULT_TEMPLATE).replace("\n", newline))


def test_confirmed_canonical_move_updates_configuration_in_same_transaction(context):
    seed(context)
    settings = Settings(context)
    settings.bootstrap()
    before = settings.get()
    old_path, new_path = before["template_path"], "root/templates/renamed.md"
    content = context.vault.read(old_path).encode()
    context.coordinator.commit({old_path: None, new_path: content},
                               {old_path: sha_bytes(content), new_path: None}, {"moves": [[old_path, new_path]]})
    context.vault.index()
    assert settings.get()["template_path"] == new_path
    assert settings.get()["revision"] == before["revision"]+1
    assert settings.snapshot()["template"]["sha256"] == sha_bytes(content)


def test_delete_recreate_is_not_a_confirmed_configuration_identity(context):
    seed(context)
    settings = Settings(context)
    settings.bootstrap()
    path = settings.get()["fallback_note"]
    content = context.vault.read(path)
    context.vault.delete(path, sha_bytes(content.encode()))
    context.vault.write(path, content, None, create=True)
    with pytest.raises(DomainError) as failure:
        settings.snapshot()
    assert failure.value.code == "CONFIGURATION_REBIND_REQUIRED"
    settings.change({"fallback_note": path, "expected_revision": settings.get()["revision"],
                     "operation_id": "explicit-rebind-pool-01"})
    assert settings.snapshot()["fallback"]["path"] == path


@pytest.mark.parametrize("change", [
    lambda s: s.replace("{{crusher.body}}", ""),
    lambda s: s+"\n{{crusher.links}}",
    lambda s: s.replace("{{title}}", "{{unsupported}}"),
    lambda s: s.replace("{{crusher.body}}", "```\n{{crusher.body}}\n```"),
    lambda s: "#main\n"+s,
    lambda s: s+"\n[[Unapproved]]",
    lambda s: s+"\n<% run() %>",
    lambda s: s+"\n<script>alert(1)</script>",
    lambda s: s+"\n[link](private.md)",
])
def test_invalid_or_executable_template_is_rejected(change):
    with pytest.raises(DomainError):
        parse(change(DEFAULT_TEMPLATE))


def test_bootstrap_keeps_existing_notes_and_is_idempotent(context):
    existing = seed(context)
    settings = Settings(context)
    result = settings.bootstrap()
    assert result["output_dir"] == "root/crusher"
    assert context.vault.read(DEFAULT_PATH) == DEFAULT_TEMPLATE
    assert "[[pool]]" in context.vault.read("root.md")
    before = {p: context.vault.read(p) for p, _ in context.vault.files()}
    assert settings.bootstrap() == result
    assert before == {p: context.vault.read(p) for p, _ in context.vault.files()}
    assert all(context.vault.read(p) == text for p, text in existing.items() if p != "root.md")
    custom = DEFAULT_TEMPLATE.replace("Кратко", "Суть")
    context.vault.write(DEFAULT_PATH, custom, sha_bytes(DEFAULT_TEMPLATE.encode()))
    settings.bootstrap()
    assert context.vault.read(DEFAULT_PATH) == custom


def test_bootstrap_missing_root_does_not_invent_graph(context):
    with pytest.raises(DomainError):
        Settings(context).bootstrap()
    assert not context.vault.files()


def test_settings_conflict_idempotency_and_snapshot(context):
    seed(context)
    settings = Settings(context)
    settings.bootstrap()
    before = settings.snapshot()
    change = {"expected_revision": before["configuration"]["revision"], "operation_id": "stable-settings-operation",
              "curator_enabled": True}
    after = settings.change(change)
    assert settings.change(change) == after
    assert before["configuration"]["curator_enabled"] is False
    with pytest.raises(DomainError) as error:
        settings.change({**change, "operation_id": "different-settings-operation"})
    assert error.value.code == "SETTINGS_CONFLICT"
    with pytest.raises(DomainError):
        settings.change({**change, "curator_enabled": False})
    with pytest.raises(DomainError):
        settings.change({"template_path": "../secret.md"}, dry_run=True)
    assert settings.get() == after


def test_generic_search_returns_ordinary_notes_and_enforces_scope(context):
    seed(context)
    pipeline = Pipeline(context, Index(context))
    result, _ = pipeline.run({"text": "polynomials factorization"})
    assert result["results"][0]["path"] == "Notes/Ordinary.md"
    restricted, _ = pipeline.run({"text": "polynomials"}, scope=Scope("owner", frozenset({"Notes/Unlinked.md"})))
    assert restricted["results"] == []
    with pytest.raises(DomainError) as error:
        pipeline.run({"text": "polynomials"}, scope=Scope("crusher-visitor"))
    assert error.value.status == 403
    trace = context.state.one("SELECT record FROM context_traces LIMIT 1")["record"]
    assert "factorization" not in trace and "excerpt" not in trace and "query\"" not in trace


def test_independent_vector_hit_without_fts(context):
    seed(context)
    graph = Graph(context.vault, Scope("owner"))

    class Vectors:
        def search(self, query, limit, **kwargs):
            assert "Notes/Unlinked.md" in kwargs["allowed_paths"]
            return {"results": [{"path": "Notes/Unlinked.md", "score": .9, "excerpt": "Nebula interstellar astronomy."}],
                    "index": {"status": "READY"}}

    result, _ = Pipeline(context, Index(context), semantic=Vectors()).run({"text": "звездные облака"})
    assert result["channels"]["fts"] == 0
    assert result["results"][0]["path"] == "Notes/Unlinked.md"
    assert result["results"][0]["sha256"] == graph.notes["Notes/Unlinked.md"]["sha"]


def test_profiles_include_incoming_member_and_invalidate_its_edit(context):
    seed(context)
    settings = Settings(context)
    settings.bootstrap()
    index = Index(context)
    graph = Graph(context.vault, Scope("owner"))
    before = index.profiles(graph, graph.structure(), settings.get())
    assert "factorization" in before["Topics/Algebra.md"]["text"]
    body = context.vault.read("Notes/Ordinary.md")
    context.vault.write("Notes/Ordinary.md", "Replacement [[Algebra]]", sha_bytes(body.encode()))
    graph = Graph(context.vault, Scope("owner"))
    after = index.profiles(graph, graph.structure(), settings.get())
    assert after["Topics/Algebra.md"]["sha256"] != before["Topics/Algebra.md"]["sha256"]
    assert "factorization" not in after["Topics/Algebra.md"]["text"]


def test_uncalibrated_placement_pools_and_keeps_file_location_independent(context):
    seed(context)
    settings = Settings(context)
    settings.bootstrap()
    policy = PlacementPolicy(settings, calibration={"qualified": False})
    result, graph = Pipeline(context, Index(context)).run({"text": "algebra polynomials equations"},
        query_type="placement_analysis", configuration=settings.get(), assessment=policy.assess)
    decision = policy.decide(result, graph, settings.snapshot())
    assert decision["outcome"] == "pooled" and decision["anchor"] == "root/pool.md"
    assert settings.get()["output_dir"] == "root/crusher"


def test_invalid_structural_nodes_stay_searchable_but_not_eligible(context):
    seed(context)
    context.vault.write("Unreachable.md", "#key\nExact orphan subject", None, create=True)
    graph = Graph(context.vault, Scope("owner"))
    assert "Unreachable.md" not in graph.structure().eligible
    result, _ = Pipeline(context, Index(context)).run({"text": "orphan subject"})
    assert result["results"][0]["path"] == "Unreachable.md"
    body = context.vault.read("Topics/Algebra.md")
    context.vault.write("Topics/Algebra.md", body+"\n[[Algebra]]", sha_bytes(body.encode()))
    assert "Topics/Algebra.md" not in Graph(context.vault, Scope("owner")).structure().eligible


def test_single_source_retrieved_twice_is_not_two_independent_votes():
    value = {"path": "a.md", "title": "Algebra", "excerpt": "Algebra", "sha256": "a"*64,
             "features": {}, "strategies": {"fts": 2}, "graph_paths": []}
    first = {"results": [value], "channels": {"fts": 1}, "missing_strategies": [], "degraded": False, "truncated": False}
    second = json.loads(json.dumps(first))
    second["results"][0]["strategies"]["fts"] = 1
    result = Pipeline.merge(first, second, {"text": "Algebra"})
    assert len(result["results"]) == 1
    assert result["results"][0]["features"]["rrf"] == 1/61
