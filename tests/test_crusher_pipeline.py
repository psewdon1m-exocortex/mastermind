import json
from types import SimpleNamespace

import pytest

from mastermind.crusher import Crusher
from mastermind.crusher_access import CrusherAccess
from mastermind.errors import DomainError
from mastermind.fs import sha_bytes
from mastermind.gemini import Choice, Understanding


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
        if schema is Choice:
            return {"action": "choose", "handle": packet["candidates"][0]["handle"], "confidence": 0.95}
        return {"title": "Useful facts", "markdown": "# Useful facts\n\nKnowledge architecture organizes information."}

    def close(self):
        pass


@pytest.fixture
def pipeline(recovery):
    backup, _, auth = recovery
    access = CrusherAccess(backup.config, backup.state, auth, backup.audit)
    service = SimpleNamespace(config=backup.config, state=backup.state, secrets=backup.secrets, kernel=None,
        vault=backup.vault, coordinator=backup.coordinator, audit=backup.audit, crusher_access=access, data_ready=lambda: None)
    engine = Crusher(service, worker=Worker(), provider=Provider())
    return engine, access, backup.vault


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
    assert len(vault.files()) == 1 and vault.files()[0][0] == "Inbox/Crusher/Useful facts.md"
    text = vault.read("Inbox/Crusher/Useful facts.md")
    assert text.count("<!-- mastermind:crusher") == 1 and accepted["job_id"] in text
    assert accept(access)["job_id"] == accepted["job_id"]
    assert not engine.once() and len(vault.files()) == 1
    assert not list(access.directory.iterdir()) and access.reserved() == 0
    assert engine.state.one("SELECT COUNT(*) AS n FROM activity")["n"] == 0
    row = engine.state.one("SELECT record FROM jobs")
    states = [step["state"] for step in json.loads(row["record"])["transitions"]]
    assert states == ["QUEUED", "ACQUIRING", "NORMALIZING", "EXTRACTING", "UNDERSTANDING", "PLACING", "GENERATING", "VALIDATING", "COMMITTING", "COMPLETED"]


def test_selected_existing_branch_and_global_basename_collision(pipeline):
    engine, access, vault = pipeline
    for path, text in {"root.md": "[[Knowledge]]", "Notes/Knowledge.md": "#main\n[[Architecture]]",
                       "Notes/Architecture.md": "#key\nKnowledge architecture.", "Other/Useful facts.md": "Already exists"}.items():
        vault.write(path, text, None, create=True)
    accept(access)
    engine.once()
    created = vault.read("Notes/Useful facts (2).md")
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
    assert len(engine.provider.calls) == 3 and not vault.files()


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
    assert len(vault.files()) == 1


def test_source_loss_and_untrusted_generated_resources_fail_before_commit(pipeline):
    engine, access, vault = pipeline
    accepted = accept(access)
    source = json.loads(engine.state.one("SELECT record FROM jobs")["record"])["local_source"]
    (access.directory / source).unlink()
    engine.once()
    assert access.status(accepted["job_id"], principal="owner")["error"]["code"] == "SOURCE_UNAVAILABLE"
    assert not vault.files()
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
