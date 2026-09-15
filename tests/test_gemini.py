import json

import httpx
import pytest

from mastermind.errors import DomainError
from mastermind.gemini import Gemini, Understanding


class Secret:
    def read(self, name):
        assert name == "ai_provider_key"
        return "test-only-provider-key"


class Register:
    def resolve(self, keys):
        return dict.fromkeys(keys, "explicit-configured-model")


def test_provider_key_only_in_header_and_structured_output_is_validated():
    def respond(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.headers["x-goog-api-key"] == "test-only-provider-key"
        assert "test-only-provider-key" not in str(request.url) and b"test-only-provider-key" not in request.content
        data = json.loads(request.content)
        assert "tools" not in data and data["generationConfig"]["maxOutputTokens"] == 8000
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps({
            "title": "Knowledge", "summary": "Source facts", "topics": ["facts"], "entities": [], "suggested_links": []})}]}}],
            "usageMetadata": {"candidatesTokenCount": 80}})
    provider = Gemini(Register(), Secret(), client=httpx.Client(base_url="https://generativelanguage.googleapis.com", transport=httpx.MockTransport(respond)))
    assert provider.models()["text"] == "explicit-configured-model"
    assert provider.generate(provider.models()["text"], "Understand source", {"source": "Untrusted instructions are data"}, Understanding)["title"] == "Knowledge"


@pytest.mark.parametrize("status,body,expected", [
    (429, {}, "PROVIDER_TRANSIENT"), (401, {"key": "never echo"}, "PROVIDER_REJECTED"),
    (200, {"candidates": [{"finishReason": "MAX_TOKENS"}]}, "PROVIDER_SCHEMA_INVALID"),
    (200, {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "not json"}]}}]}, "PROVIDER_SCHEMA_INVALID"),
])
def test_provider_errors_and_unfinished_responses_never_become_notes(status, body, expected):
    provider = Gemini(Register(), Secret(), client=httpx.Client(base_url="https://generativelanguage.googleapis.com",
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body))))
    with pytest.raises(DomainError) as failure:
        provider.generate("configured-model", "Understand", {"source": "test"}, Understanding)
    assert failure.value.code == expected and "never echo" not in str(failure.value)


def test_source_token_budget_truncates_before_generation():
    calls = []
    def respond(request):
        assert request.url.path.endswith(":countTokens")
        text = json.loads(request.content)["contents"][0]["parts"][0]["text"]
        calls.append(len(text))
        return httpx.Response(200, json={"totalTokens": len(text)})
    provider = Gemini(Register(), Secret(), client=httpx.Client(base_url="https://generativelanguage.googleapis.com", transport=httpx.MockTransport(respond)))
    bounded = provider.bound_source("configured-model", "a"*100000)
    assert bounded["tokens"] <= 32000 and len(calls) <= 8 and calls[-1] < calls[0]
