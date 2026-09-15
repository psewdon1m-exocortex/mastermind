import json
from contextlib import contextmanager

import httpx
import pytest
from test_gemini import Register, Secret

from mastermind.errors import DomainError
from mastermind.gemini import Gemini

ORIGIN = "https://generativelanguage.googleapis.com"
FILE = {"name": "files/test-media", "uri": ORIGIN + "/v1beta/files/test-media", "state": "ACTIVE"}


class Media:
    size = 12

    @contextmanager
    def media(self, identifier):
        assert identifier == "a"*32
        yield {"size": self.size, "blocks": iter([b"media-", b"source"])}


def fixture(responder):
    def streaming(request):
        response = responder(request)
        return httpx.Response(response.status_code, headers=response.headers, stream=httpx.ByteStream(response.content))
    return Gemini(Register(), Secret(), client=httpx.Client(base_url=ORIGIN, transport=httpx.MockTransport(streaming)))


def test_streamed_media_upload_understanding_and_remote_cleanup():
    requests, saved, budget = [], {}, {"source_transmitted": 0}

    def respond(request):
        requests.append((request.method, request.url.path))
        assert request.headers["x-goog-api-key"] == "test-only-provider-key"
        if request.url.path == "/upload/v1beta/files":
            if request.headers["x-goog-upload-command"] == "start":
                assert request.headers["x-goog-upload-header-content-length"] == "12"
                return httpx.Response(200, headers={"x-goog-upload-url": ORIGIN + "/upload/v1beta/files?upload_id=opaque-canary"})
            assert request.read() == b"media-source"
            assert request.headers["x-goog-upload-offset"] == "0"
            return httpx.Response(200, json={"file": FILE})
        if request.method == "DELETE":
            return httpx.Response(204)
        packet = json.loads(request.content)
        part = packet["contents"][0]["parts"][-1]
        assert part["fileData"]["fileUri"] == FILE["uri"]
        if request.url.path.endswith(":countTokens"):
            return httpx.Response(200, json={"totalTokens": 400})
        result = {"title": "Media facts", "summary": "Spoken source facts.", "topics": [], "entities": [], "suggested_links": []}
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(result)}]}}],
                                       "usageMetadata": {"candidatesTokenCount": 80}})

    def checkpoint(key, action):
        if key not in saved:
            saved[key] = action()
        return saved[key]

    provider = fixture(respond)
    result = provider.understand_media("configured-model", "a"*32, {"type": "audio", "mime": "audio/mpeg"},
                                       Media(), checkpoint, budget, lambda: None)
    assert result["title"] == "Media facts" and budget["source_transmitted"] == 1400
    assert "opaque-canary" not in json.dumps(saved)
    provider.cleanup_media({"results": saved})
    assert requests[-1] == ("DELETE", "/v1beta/files/test-media")
    assert requests.count(("POST", "/upload/v1beta/files")) == 2


@pytest.mark.parametrize("url", ["https://evil.test/upload/v1beta/files", "http://generativelanguage.googleapis.com/upload/v1beta/files",
    ORIGIN + ":bad/upload/v1beta/files", ORIGIN + "/v1beta/files", "https://user@generativelanguage.googleapis.com/upload/v1beta/files"])
def test_provider_cannot_redirect_source_or_key_to_another_upload_endpoint(url):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, headers={"x-goog-upload-url": url})
    with pytest.raises(DomainError) as failure:
        fixture(respond).upload_media("a"*32, "audio/mpeg", Media())
    assert failure.value.code == "PROVIDER_RESPONSE_INVALID" and len(calls) == 1


def test_scanned_pdf_limit_is_checked_before_any_provider_upload():
    media = Media()
    media.size = 50*1024**2+1
    def forbidden(request):
        raise AssertionError("No provider request may occur")
    with pytest.raises(DomainError) as failure:
        fixture(forbidden).upload_media("a"*32, "application/pdf", media)
    assert failure.value.code == "PROVIDER_MEDIA_LIMIT"


def test_processing_file_cannot_change_identity(monkeypatch):
    monkeypatch.setattr("mastermind.gemini.time.sleep", lambda seconds: None)
    changed = {**FILE, "name": "files/another", "uri": ORIGIN + "/v1beta/files/another"}
    provider = fixture(lambda request: httpx.Response(200, json=changed))
    with pytest.raises(DomainError) as failure:
        provider.wait_media({**FILE, "state": "PROCESSING"})
    assert failure.value.code == "PROVIDER_RESPONSE_INVALID"


def test_youtube_clipping_is_explicit_and_counted_before_generation():
    packets = []
    provider = fixture(lambda request: (_ for _ in ()).throw(AssertionError("Unexpected transport")))
    provider.token_count = lambda model, **options: 800 if "videoMetadata" in options["parts"][0] else 100000
    provider.generate = lambda model, task, packet, schema, **options: packets.append((packet, options)) or {"summary": "Initial excerpt"}
    budget = {"source_transmitted": 0}
    provider.understand_media("configured-model", "a"*32, {"type": "youtube", "youtube": "https://youtu.be/abcdefghijk"},
                              Media(), lambda key, action: action(), budget, lambda: None)
    assert packets[0][0]["initial_excerpt_only"] is True
    part = packets[0][1]["media_parts"][0]
    assert part["videoMetadata"]["endOffset"] == "120s" and budget["source_transmitted"] == 1800
    assert part["fileData"]["fileUri"] == "https://www.youtube.com/watch?v=abcdefghijk"
