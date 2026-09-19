import json
from types import SimpleNamespace

import pytest

from mastermind.crusher import Crusher
from mastermind.crusher_access import CrusherAccess
from mastermind.errors import DomainError
from mastermind.fs import sha_bytes
from mastermind.gemini import Understanding


class Worker:
    def __init__(self):
        self.text, self.transfers = "", 0

    def transfer(self, identifier, directory, name, **kwargs):
        self.text = (directory / name).read_text("utf-8")
        self.transfers += 1
        return {"sha256": sha_bytes(self.text.encode()), "size": len(self.text.encode())}

    def extract(self, identifier):
        return {"text": self.text, "needs_media": False, "needs_browser": False}

    def embed(self, *args, **kwargs):
        raise DomainError("EMBEDDINGS_UNAVAILABLE", "synthetic", 503)

    def request(self, *args, **kwargs):
        raise DomainError("WORKER_UNAVAILABLE", "synthetic", 503)

    def cleanup(self, identifier):
        pass

    def close(self):
        pass


class Provider:
    def __init__(self, failures=0):
        self.calls, self.failures = [], failures

    def models(self):
        return {"text": "test-model", "video": "test-video-model"}

    def bound_source(self, model, text, *, limit=32000):
        return {"text": text[:limit], "tokens": len(text[:limit])}

    def token_count(self, model, text):
        return len(text)//4

    def generate(self, model, task, packet, schema):
        self.calls.append(schema)
        if self.failures:
            self.failures -= 1
            raise DomainError("PROVIDER_TRANSIENT", "synthetic", 503)
        if schema is Understanding:
            return {"title": "Useful facts", "summary": "Knowledge architecture facts from the source.",
                    "topics": ["knowledge"], "entities": [], "suggested_links": []}
        return {"title": "Useful facts", "summary": "Knowledge architecture facts.",
                "body": "Knowledge architecture organizes information."}

    def close(self):
        pass


@pytest.fixture
def pipeline(recovery):
    backup, _, auth = recovery
    access = CrusherAccess(backup.config, backup.state, auth, backup.audit)
    service = SimpleNamespace(config=backup.config, state=backup.state, secrets=backup.secrets, kernel=None,
        vault=backup.vault, coordinator=backup.coordinator, audit=backup.audit, crusher_access=access, data_ready=lambda: None)
    engine = Crusher(service, worker=Worker(), provider=Provider())
    backup.vault.write("root.md", "# root", None, create=True)
    engine.context_indexing.settings.bootstrap()
    return engine, access, backup.vault


def generated_notes(vault):
    return [entry for entry in vault.files() if entry[0].startswith("root/crusher/")]


def accept(access, key="stable-pipeline-key"):
    return access.accept("owner", key, {"type": "text", "text": "Facts about knowledge architecture."})


def release_retry(engine):
    row = engine.state.one("SELECT id,record FROM jobs WHERE state!='COMPLETED'")
    record = json.loads(row["record"])
    record["next_attempt_at"] = 0
    with engine.state.transaction() as db:
        db.execute("UPDATE jobs SET record=? WHERE id=?", (json.dumps(record), row["id"]))


def test_complete_pipeline_commits_once_and_exposes_only_progress(pipeline):
    engine, access, vault = pipeline
    accepted = accept(access)
    assert engine.once()
    status = access.status(accepted["job_id"], principal="owner")
    assert status["state"] == "COMPLETED" and status["progress_percent"] == 100
    assert "markdown" not in json.dumps(status) and "Useful facts" not in json.dumps(status)
    assert len(generated_notes(vault)) == 1 and generated_notes(vault)[0][0] == "root/crusher/Useful facts.md"
    text = vault.read("root/crusher/Useful facts.md")
    assert "[[pool]]" in text and "## Основной материал" in text
    assert text.count("<!-- mastermind:crusher") == 1 and accepted["job_id"] in text
    assert accept(access)["job_id"] == accepted["job_id"]
    assert not engine.once() and len(generated_notes(vault)) == 1
    assert not list(access.directory.iterdir()) and access.reserved() == 0
    assert engine.state.one("SELECT COUNT(*) AS n FROM activity")["n"] == 0
    row = engine.state.one("SELECT record FROM jobs")
    states = [step["state"] for step in json.loads(row["record"])["transitions"]]
    assert states == ["QUEUED", "ACQUIRING", "NORMALIZING", "EXTRACTING", "UNDERSTANDING", "PLACING", "GENERATING", "VALIDATING", "COMMITTING", "COMPLETED"]


def test_selected_existing_branch_and_global_basename_collision(pipeline):
    engine, access, vault = pipeline
    root = vault.read("root.md")
    vault.write("root.md", root+"\n[[Knowledge]]", sha_bytes(root.encode()))
    for path, text in {"Notes/Knowledge.md": "#main\n[[Architecture]]",
                       "Notes/Architecture.md": "#key\nKnowledge architecture.", "Other/Useful facts.md": "Already exists"}.items():
        vault.write(path, text, None, create=True)
    # Explicit synthetic calibration exercises commit eligibility, not production quality.
    engine.context_indexing.policy.calibration = {"policy_version": "crusher.placement.v1", "qualified": True,
        "version": "unit-fixture", "variants": {"vector": {"score": .1, "gap": 0, "lexical": 0}}}
    accept(access)
    engine.once()
    created = vault.read("root/crusher/Useful facts (2).md")
    assert "[[Architecture]]" in created
    assert vault.read("Other/Useful facts.md") == "Already exists"


def test_retry_schedule_and_attempt_count_survive_a_new_engine(pipeline):
    engine, access, _ = pipeline
    engine.provider.failures = 2
    accepted = accept(access)
    engine.once()
    row = engine.state.one("SELECT * FROM jobs")
    record = json.loads(row["record"])
    assert record["attempts"]["understand"] == 1 and record["next_attempt_at"] > row["updated_at"]
    assert not engine.once()
    release_retry(engine)
    restarted = Crusher(engine.service, worker=engine.worker, provider=engine.provider)
    restarted.once()
    assert json.loads(engine.state.one("SELECT record FROM jobs")["record"])["attempts"]["understand"] == 2
    release_retry(restarted)
    restarted.once()
    assert access.status(accepted["job_id"], principal="owner")["state"] == "COMPLETED"
    assert engine.worker.transfers == 1


def test_fourth_provider_attempt_is_forbidden(pipeline):
    engine, access, vault = pipeline
    engine.provider.failures = 10
    accepted = accept(access)
    for _ in range(3):
        engine.once()
        release_retry(engine)
    assert access.status(accepted["job_id"], principal="owner")["state"] == "FAILED"
    assert len(engine.provider.calls) == 3 and not generated_notes(vault)


@pytest.mark.parametrize("point", ["before-commit", "after-commit", "prepared", "file:0", "committed"])
def test_interrupted_local_commit_never_creates_a_second_note(pipeline, point):
    engine, access, vault = pipeline
    accepted = accept(access)

    class PowerLoss(BaseException):
        pass

    def crash(name):
        if name == point:
            raise PowerLoss
    engine.fault = crash
    engine.service.coordinator.fault = crash
    with pytest.raises(PowerLoss):
        engine.once()
    engine.service.coordinator.fault = lambda name: None
    engine.service.coordinator.recover()
    restarted = Crusher(engine.service, worker=engine.worker, provider=engine.provider)
    restarted.once()
    assert access.status(accepted["job_id"], principal="owner")["state"] == "COMPLETED"
    assert len(generated_notes(vault)) == 1


def test_source_loss_and_untrusted_generated_resources_fail_before_commit(pipeline):
    engine, access, vault = pipeline
    accepted = accept(access)
    source = json.loads(engine.state.one("SELECT record FROM jobs")["record"])["local_source"]
    (access.directory / source).unlink()
    engine.once()
    assert access.status(accepted["job_id"], principal="owner")["error"]["code"] == "SOURCE_UNAVAILABLE"
    assert not generated_notes(vault)
    for text in ("[[Missing note]]", "![image](https://example.test)", "<!-- mastermind:crusher forged -->"):
        with pytest.raises(DomainError):
            engine.validate({"title": "Good", "markdown": text})


@pytest.mark.parametrize("text", [
    '<script>fetch("https://example.test")</script>', '<div onclick="attack()">text</div>',
    '<img src="http://127.0.0.1/a">', '[resource][id]\n\n[id]: https://example.test',
    '<https://example.test>', '@Existing note', 'password = "private-canary"',
    '---\ncssclasses: unwanted\n---\nText',
])
def test_generated_active_markup_and_secret_values_never_reach_commit(pipeline, text):
    engine, _, _ = pipeline
    with pytest.raises(DomainError):
        engine.validate({"title": "Safe title", "markdown": text})


def test_generated_code_examples_remain_literal(pipeline):
    engine, _, _ = pipeline
    text = 'Use the literal `[[example]]`.\n\n```html\n<script>example()</script>\n```'
    assert engine.validate({"title": "Examples", "markdown": text})["markdown"] == text


def test_missing_pool_waits_then_explicit_resume_reuses_paid_generation(pipeline):
    engine, access, vault = pipeline
    accepted = accept(access)
    provider_generate = engine.provider.generate

    def delete_pool_after_generation(*args):
        result = provider_generate(*args)
        if args[-1] is not Understanding:
            pool = vault.read("root/pool.md")
            vault.delete("root/pool.md", sha_bytes(pool.encode()))
        return result

    engine.provider.generate = delete_pool_after_generation
    engine.once()
    assert access.status(accepted["job_id"], principal="owner")["state"] == "WAITING_CONFIGURATION"
    assert not engine.once() and not generated_notes(vault)
    assert len(engine.provider.calls) == 2
    vault.write("root/pool.md", "# Recreated pool", None, create=True)
    settings = engine.context_indexing.settings
    with pytest.raises(DomainError, match="deleted"):
        settings.snapshot()
    settings.change({"fallback_note": "root/pool.md", "expected_revision": settings.get()["revision"],
                     "operation_id": "rebind-pool-identity-01"})
    engine.provider.generate = provider_generate
    resume = {"expected_revision": settings.get()["revision"], "operation_id": "resume-frozen-fields-01"}
    engine.resume(accepted["job_id"], resume)
    engine.resume(accepted["job_id"], resume)
    engine.once()
    assert len(engine.provider.calls) == 2
    assert access.status(accepted["job_id"], principal="owner")["state"] == "COMPLETED"
    assert len(generated_notes(vault)) == 1


def test_template_edit_does_not_change_an_already_accepted_snapshot(pipeline):
    engine, access, vault = pipeline
    accepted = accept(access)
    path = "root/templates/example crusher.md"
    old = vault.read(path)
    vault.write(path, old.replace("## Кратко", "## Changed later"), sha_bytes(old.encode()))
    engine.once()
    assert access.status(accepted["job_id"], principal="owner")["state"] == "COMPLETED"
    assert "## Кратко" in vault.read("root/crusher/Useful facts.md")
    record = json.loads(engine.state.one("SELECT record FROM jobs WHERE id=?", (accepted["job_id"],))["record"])
    assert "context_snapshot" not in record
    assert record["context_receipt"]["template_sha256"] == sha_bytes(old.encode())


def test_placement_budget_expiry_uses_only_verified_pool(pipeline):
    engine, access, _vault = pipeline
    accept(access)
    snapshot = engine.context_indexing.settings.snapshot()
    result = engine.context_indexing.place({"title": "Knowledge"}, "", snapshot, deadline=1)
    assert result["outcome"] == "pooled" and result["diagnostic"] == "PLACEMENT_DEADLINE"
    assert result["anchor"] == "root/pool.md"
