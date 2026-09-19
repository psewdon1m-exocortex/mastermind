import copy
import time

import pytest

from mastermind.context_indexing.curator import Curator
from mastermind.context_indexing.pipeline import Pipeline, explicitly_negated
from mastermind.curator_runtime import LocalCurator
from mastermind.errors import DomainError


class Worker:
    def __init__(self, proposal=None, ready=True, failure=None):
        self.calls, self.ready, self.failure = 0, ready, failure
        self.proposal = proposal or {"terms": ["photosynthesis"], "evidence_handles": ["e0"], "request_second_pass": True}

    def request(self, method, path, *args, **kwargs):
        if path.endswith("status"):
            return {"schema": "context-indexing.curator.v1", "ready": self.ready, "model_digest": "a"*64}
        self.calls += 1
        if self.failure:
            raise DomainError(self.failure, "Synthetic failure", 408)
        return {"model_digest": "a"*64, "proposal": self.proposal}


SUBJECT = {"text": "Plants using sunlight"}
RESULT = {"results": [{"title": "Biology", "excerpt": "Photosynthesis"}]}
ASSESSMENT = {"status": "ambiguous", "reason": "LOW_EVIDENCE"}


def journal():
    values = {}

    def checkpoint(key, action):
        if key not in values:
            values[key] = action()
        return copy.deepcopy(values[key])
    return values, checkpoint


def test_real_call_reservation_is_reused_across_resume_without_second_inference():
    worker = Worker()
    curator = Curator(worker)
    _, checkpoint = journal()
    first = curator.refine(SUBJECT, RESULT, ASSESSMENT, checkpoint=checkpoint)
    second = Curator(worker).refine(SUBJECT, RESULT, ASSESSMENT, checkpoint=checkpoint)
    assert worker.calls == 1 and first == second
    assert "photosynthesis" in first[0]["text"]


def test_reserved_call_interrupted_before_response_is_never_reissued():
    worker = Worker()
    values, checkpoint = journal()

    class Crash(BaseException):
        pass

    def crashed(key, action):
        value = checkpoint(key, action)
        if key == "context_curator_reservation":
            raise Crash
        return value

    with pytest.raises(Crash):
        Curator(worker).refine(SUBJECT, RESULT, ASSESSMENT, checkpoint=crashed)
    proposal, status = Curator(worker).refine(SUBJECT, RESULT, ASSESSMENT, checkpoint=checkpoint)
    assert proposal is None and status["outcome"] == "interrupted" and worker.calls == 0
    assert "context_curator_response" in values


@pytest.mark.parametrize("change", [
    {"evidence_handles": ["outside-scope"]}, {"evidence_handles": [[]]},
    {"terms": ["x"]*9}, {"terms": [42]}, {"request_second_pass": "true"},
    {"destination": "root/private.md"},
])
def test_curator_cannot_supply_authority_or_unknown_evidence(change):
    worker = Worker()
    worker.proposal.update(change)
    refined, status = Curator(worker).refine(SUBJECT, RESULT, ASSESSMENT)
    assert refined is None and status["outcome"] == "invalid_proposal"


@pytest.mark.parametrize("failure,outcome", [("CURATOR_TIMEOUT", "timeout"), ("CURATOR_UNAVAILABLE", "unavailable")])
def test_curator_failure_is_bounded_and_explicit(failure, outcome):
    worker = Worker(failure=failure)
    _, checkpoint = journal()
    for _ in range(2):
        refined, status = Curator(worker).refine(SUBJECT, RESULT, ASSESSMENT, checkpoint=checkpoint)
        assert refined is None and status["outcome"] == outcome
    assert worker.calls == 1


def test_unavailable_or_expired_budget_does_not_infer():
    for worker, deadline in [(Worker(ready=False), None), (Worker(), time.monotonic()-1)]:
        assert Curator(worker).refine(SUBJECT, RESULT, ASSESSMENT, deadline=deadline)[0] is None
        assert worker.calls == 0


def test_runtime_validates_context_before_start_or_network(tmp_path):
    runtime = LocalCurator(tmp_path, tmp_path/"missing-lock")
    for context in [{}, {"query": "x"*3001, "candidates": [], "reason": "test"},
                    {"query": "valid", "candidates": [{"handle": "x", "title": "T", "excerpt": "x"*701}], "reason": "test"}]:
        with pytest.raises(DomainError) as error:
            runtime.assist(context)
        assert error.value.code == "CURATOR_CONTEXT_LIMIT"
    assert runtime.status()["ready"] is False


def test_second_pass_union_deduplicates_all_channel_provenance():
    def entry(path, strategy, rank):
        return {"path": path, "title": "photosynthesis", "excerpt": "plants sunlight", "strategies": {strategy: rank}, "features": {}}
    first = {"results": [entry("a.md", "fts", 1)], "channels": {"fts": 1}, "missing_strategies": [], "degraded": False, "truncated": False}
    second = {**first, "results": [entry("a.md", "vector", 2), entry("b.md", "entity", 1)], "channels": {"vector": 1, "entity": 1}}
    merged = Pipeline.merge(first, second, SUBJECT)
    assert len(merged["results"]) == 2
    assert next(v for v in merged["results"] if v["path"] == "a.md")["strategies"] == {"fts": 1, "vector": 2}


def test_explicit_negative_topic_mention_is_counter_evidence_not_an_instruction():
    assert explicitly_negated("Algebra", "No evidence about algebra is given.")
    assert explicitly_negated("biology", "The source is unrelated to biology.")
    assert explicitly_negated("алгебры", "Это не касается алгебры.")
    assert not explicitly_negated("Algebra", "No evidence about geometry. Algebra explains matrices.")
    assert not explicitly_negated("Algebra", "We found evidence about algebra.")
