import json

import pytest

from mastermind.errors import DomainError
from mastermind.hierarchy import Hierarchy


class LocalWorker:
    def embed(self, *args, **kwargs):
        raise DomainError("EMBEDDINGS_UNAVAILABLE", "Synthetic outage", 503)


class Provider:
    def __init__(self, decision=None, token_cost=100):
        self.calls, self.decision, self.token_cost = [], decision, token_cost

    def token_count(self, model, text):
        return self.token_cost

    def generate(self, model, task, packet, schema):
        self.calls.append(packet)
        return self.decision or {"action": "choose", "handle": packet["candidates"][0]["handle"], "confidence": 0.95}


def place(vault, provider):
    results, budget = {}, {"unique": {}, "transmitted": 0}

    def checkpoint(key, action, *, persist_only=False):
        if persist_only:
            return None
        if key not in results:
            results[key] = action()
        return results[key]

    hierarchy = Hierarchy(vault, LocalWorker(), provider)
    output = hierarchy.place({"summary": "Mathematics and algebra", "topics": ["algebra"]}, "configured-model",
                              checkpoint=checkpoint, budget=budget)
    return output, hierarchy, budget


def seed(vault, *, extra=None):
    notes = {"root.md": "[[Mathematics]]\n[[Other]]", "Science/Mathematics.md": "#main\n\n[[Algebra]]\n",
             "Science/Algebra.md": "#key\n\nAlgebra facts.", "Elsewhere/Other.md": "#main\nOther subject.",
             "Elsewhere/Private ordinary note.md": "DO_NOT_DISCLOSE_ORDINARY_NOTE"}
    notes.update(extra or {})
    for path, text in notes.items():
        vault.write(path, text, None, create=True)


def test_current_level_only_handles_and_fts_without_embeddings(service):
    vault = service[3]
    seed(vault)
    provider = Provider()
    output, _, budget = place(vault, provider)
    assert output["anchor"] == "Science/Algebra.md" and output["confidence"] == 0.95
    assert len(provider.calls) == 2
    assert {card["title"] for card in provider.calls[0]["candidates"]} == {"Mathematics", "Other"}
    assert {card["title"] for card in provider.calls[1]["candidates"]} == {"Algebra"}
    exposed = json.dumps(provider.calls)
    assert "DO_NOT_DISCLOSE" not in exposed and "Science/" not in exposed and "Elsewhere/" not in exposed
    assert all(len(card["excerpt"]) <= 512 and "path" not in card for call in provider.calls for card in call["candidates"])
    assert sum(budget["unique"].values()) <= 12000 and budget["transmitted"] <= 24000


@pytest.mark.parametrize("extra,diagnostic", [
    ({"Science/Mathematics.md": "#main\n[[Algebra]]\n[[Second parent]]", "Science/Second parent.md": "#key\n[[Algebra]]"}, "AMBIGUOUS_HIERARCHY"),
    ({"Science/Algebra.md": "#key\n[[Algebra]]"}, "AMBIGUOUS_HIERARCHY"),
    ({"Science/Algebra.md": "#main #key\nAlgebra"}, "AMBIGUOUS_HIERARCHY"),
])
def test_ambiguous_paths_cycles_and_conflicting_roles_go_to_inbox(service, extra, diagnostic):
    vault = service[3]
    seed(vault, extra=extra)
    output, _, _ = place(vault, Provider())
    assert output["anchor"] is None and output["diagnostic"] == diagnostic


def test_missing_root_and_budget_exhaustion_go_to_inbox(service):
    vault = service[3]
    output, _, _ = place(vault, Provider())
    assert output["diagnostic"] == "ROOT_MISSING"
    seed(vault)
    provider = Provider(token_cost=13000)
    output, _, _ = place(vault, provider)
    assert output["diagnostic"] == "CONTEXT_BUDGET" and not provider.calls


def test_unknown_handle_is_never_a_filesystem_authority(service):
    vault = service[3]
    seed(vault)
    provider = Provider({"action": "choose", "handle": "../../escape.md", "confidence": 1.0})
    with pytest.raises(DomainError) as failure:
        place(vault, provider)
    assert failure.value.code == "PLACEMENT_INVALID"


def test_hierarchy_change_before_commit_cannot_keep_old_authority(service):
    vault = service[3]
    seed(vault)
    output, hierarchy, _ = place(vault, Provider())
    assert hierarchy.revalidate(output)["anchor"]
    note = vault.read("Science/Algebra.md")
    from mastermind.fs import sha_bytes
    vault.write("Science/Algebra.md", "Removed branch tag", sha_bytes(note.encode()))
    result = hierarchy.revalidate(output)
    assert result["anchor"] is None and result["diagnostic"] == "HIERARCHY_CHANGED"


def test_at_most_twelve_cards_and_eight_levels(service):
    vault = service[3]
    notes = {"root.md": "\n".join(f"[[Branch {i}]]" for i in range(16))}
    notes.update({f"Branch {i}.md": "#main\n[[Key 0]]" if i == 0 else "#main\nOther" for i in range(16)})
    notes.update({f"Key {i}.md": "#key\n" + (f"[[Key {i+1}]]" if i < 9 else "Done") for i in range(10)})
    for path, text in notes.items():
        vault.write(path, text, None, create=True)
    provider = Provider()
    output, _, _ = place(vault, provider)
    assert all(len(call["candidates"]) <= 12 for call in provider.calls)
    assert len(provider.calls) <= 8 and output["diagnostic"] == "HIERARCHY_DEPTH_LIMIT"
