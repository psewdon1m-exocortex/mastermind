"""At-most-once local Curator proposals with a strict evidence/authority boundary."""
import time

from ..errors import DomainError
from .graph import digest
from .pipeline import bounded


class Curator:
    def __init__(self, worker):
        self.worker = worker
        self.cached = None

    def status(self):
        if self.cached and time.monotonic()-self.cached[0] < 5:
            return self.cached[1]
        try:
            value = self.worker.request("GET", "/curator/status", timeout=3)
            if value.get("schema") != "context-indexing.curator.v1" or type(value.get("ready")) is not bool:
                raise ValueError
            value = {k: value.get(k) for k in ("ready", "model_digest", "reason")}
        except (DomainError, AttributeError, ValueError):
            value = {"ready": False, "reason": "CURATOR_UNAVAILABLE", "model_digest": None}
        self.cached = time.monotonic(), value
        return value

    def refine(self, subject, result, assessment, *, checkpoint=None, deadline=None):
        status = self.status()
        outcome = {"requested": True, "effective": status["ready"], "invoked": False, "passes": 0,
                   "outcome": "unavailable", "model_digest": status["model_digest"], "reason": assessment.get("reason")}
        if not status["ready"] or deadline and deadline-time.monotonic() < 1:
            return None, outcome
        cards = [{"handle": "e"+str(i), "title": v["title"], "excerpt": bounded(v["excerpt"], 700)}
                 for i, v in enumerate(result["results"][:8])]
        context = {"query": bounded(subject["text"], 3000), "candidates": cards,
                   "reason": assessment.get("reason", assessment["status"])}
        input_hash = digest(context)
        local = {}

        def memory(key, action):
            if key not in local:
                local[key] = action()
            return local[key]

        checkpoint = checkpoint or memory
        reserved_now = []

        def reserve():
            reserved_now.append(True)
            return {"input_hash": input_hash, "model_digest": status["model_digest"]}

        reservation = checkpoint("context_curator_reservation", reserve)
        if reservation["input_hash"] != input_hash:
            outcome["outcome"] = "interrupted"
            return None, outcome

        def invoke():
            if not reserved_now:
                return {"failure": "interrupted"}
            try:
                response = self.worker.request("POST", "/curator/assist", context,
                    timeout=max(.1, min(45, (deadline or time.monotonic()+45)-time.monotonic())), limit=16*1024)
                if response.get("model_digest") != reservation["model_digest"]:
                    return {"failure": "unavailable"}
                return response
            except DomainError as error:
                return {"failure": "timeout" if "TIMEOUT" in error.code else "unavailable"}

        response = checkpoint("context_curator_response", invoke)
        outcome.update(invoked=True, passes=1)
        if response.get("failure"):
            outcome["outcome"] = response["failure"]
            return None, outcome
        proposal = response.get("proposal")
        if not isinstance(proposal, dict) or set(proposal) != {"terms", "evidence_handles", "request_second_pass"} \
                or type(proposal["request_second_pass"]) is not bool \
                or not isinstance(proposal["terms"], list) or len(proposal["terms"]) > 8 \
                or any(not isinstance(v, str) or not 1 <= len(v) <= 120 or any(ord(c) < 32 for c in v) for v in proposal["terms"]) \
                or not isinstance(proposal["evidence_handles"], list) or len(proposal["evidence_handles"]) > 8 \
                or any(not isinstance(v, str) or v not in {c["handle"] for c in cards} for v in proposal["evidence_handles"]):
            outcome["outcome"] = "invalid_proposal"
            return None, outcome
        terms = [v for v in proposal["terms"] if v.casefold() not in subject["text"].casefold()]
        if not proposal["request_second_pass"] or not terms:
            outcome["outcome"] = "no_improvement"
            return None, outcome
        outcome["outcome"] = "refined"
        return {**subject, "text": bounded(subject["text"]+"\n"+" ".join(terms), 16*1024)}, outcome
