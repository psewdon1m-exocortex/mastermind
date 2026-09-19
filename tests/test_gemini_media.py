import json
from contextlib import contextmanager

import httpx
import pytest
from test_gemini import fixture, TARGET

from mastermind.errors import DomainError
from mastermind.gemini import Gemini

FILE = {"media_id": "media_"+"a"*8+"-"+"b"*4+"-"+"c"*4+"-"+"d"*4+"-"+"e"*12, "state": "active"}


class Media:
    size = 12

    @contextmanager
    def media(self, identifier):
        assert identifier == "a"*32
        yield {"size": self.size, "blocks": iter([b"media-", b"source"])}


def test_streamed_media_upload_understanding_and_remote_cleanup(tmp_path):
    requests, saved, budget = [], {}, {"source_transmitted": 0}

    def respond(request):
        requests.append((request.method, request.url.path))
        assert "x-goog-api-key" not in request.headers
        if request.url.path.endswith("/media"):
            assert request.read() == b"media-source" and request.headers["x-wyvern-function"] == "media"
            return httpx.Response(201, json=FILE)
        if request.method == "GET":
            return httpx.Response(200, json=FILE)
        if request.method == "DELETE":
            return httpx.Response(200, json={"deleted":True})
        packet = json.loads(request.content)
        part = packet["messages"][-1]["content"][-1]
        assert part["media_id"] == FILE["media_id"]
        if request.url.path.endswith("/count-tokens"):
            return httpx.Response(200, json={"input_tokens": 400})
        result = {"title": "Media facts", "summary": "Spoken source facts.", "topics": [], "entities": [], "suggested_links": []}
        return httpx.Response(200, json={"finish_reason":"stop","json":result,"usage":{"output_tokens":80},"target":TARGET})

    def checkpoint(key, action):
        if key not in saved:
            saved[key] = action()
        return saved[key]

    provider = fixture(tmp_path, respond)
    result = provider.understand_media("media", "a"*32, {"type": "audio", "mime": "audio/mpeg"},
                                       Media(), checkpoint, budget, lambda: None)
    assert result["title"] == "Media facts" and budget["source_transmitted"] == 1400
    assert "opaque-canary" not in json.dumps(saved)
    provider.cleanup_media({"results": saved})
    assert requests[-1] == ("DELETE", "/wyvern/v1/media/"+FILE["media_id"])
    assert requests.count(("POST", "/wyvern/v1/media")) == 1


def test_scanned_pdf_limit_is_checked_before_any_provider_upload(tmp_path):
    media = Media()
    media.size = 50*1024**2+1
    def forbidden(request):
        raise AssertionError("No provider request may occur")
    with pytest.raises(DomainError) as failure:
        fixture(tmp_path, forbidden).upload_media("a"*32, "application/pdf", media)
    assert failure.value.code == "PROVIDER_MEDIA_LIMIT"


def test_processing_file_cannot_change_identity(tmp_path, monkeypatch):
    monkeypatch.setattr("mastermind.gemini.time.sleep", lambda seconds: None)
    changed = {**FILE, "media_id": "media_" + FILE["media_id"][6:].replace("a", "b")}
    provider = fixture(tmp_path, lambda request: httpx.Response(200, json=changed))
    with pytest.raises(DomainError) as failure:
        provider.wait_media({**FILE, "state": "processing"})
    assert failure.value.code == "PROVIDER_RESPONSE_INVALID"


def test_youtube_clipping_is_explicit_and_counted_before_generation(tmp_path):
    packets = []
    provider = fixture(tmp_path, lambda request: (_ for _ in ()).throw(AssertionError("Unexpected transport")))
    provider.token_count = lambda model, **options: 800 if "video" in options["parts"][0] else 100000
    provider.generate = lambda model, task, packet, schema, **options: packets.append((packet, options)) or {"summary": "Initial excerpt"}
    budget = {"source_transmitted": 0}
    provider.understand_media("media", "a"*32, {"type": "youtube", "youtube": "https://youtu.be/abcdefghijk"},
                              Media(), lambda key, action: action(), budget, lambda: None)
    assert packets[0][0]["initial_excerpt_only"] is True
    part = packets[0][1]["media_parts"][0]
    assert part["video"]["end_seconds"] == 120 and budget["source_transmitted"] == 1800
    assert part["url"] == "https://www.youtube.com/watch?v=abcdefghijk"
