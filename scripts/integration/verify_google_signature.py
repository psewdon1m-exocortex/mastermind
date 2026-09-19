"""Offline regression checks against the patched, deployed pre-Wyvern image."""
import json
import unittest

import httpx

from mastermind.errors import DomainError
from mastermind.gemini import Gemini, Understanding

VALUE = {"title": "Cedar", "summary": "Three branches and ten key notes.",
         "topics": ["knowledge"], "entities": [], "suggested_links": []}


class Secrets:
    def read(self, name):
        assert name == "ai_provider_key"
        return "synthetic-test-only"


class SignatureTests(unittest.TestCase):
    def generate(self, parts, *, finish="STOP", usage=50, status=200):
        def respond(request):
            assert request.headers["x-goog-api-key"] == "synthetic-test-only"
            assert "synthetic-test-only" not in request.content.decode()
            data = {"candidates": [{"finishReason": finish, "content": {"parts": parts}}],
                    "usageMetadata": {"candidatesTokenCount": usage}}
            return httpx.Response(status, stream=httpx.ByteStream(json.dumps(data).encode()))
        with httpx.Client(base_url="https://generativelanguage.googleapis.com",
                          transport=httpx.MockTransport(respond)) as client:
            return Gemini(None, Secrets(), client=client).generate(
                "gemini-3.8-flash", "Understand", {"source": "Synthetic facts"}, Understanding)

    def test_plain_and_signed_final_text(self):
        for signature in ({}, {"thoughtSignature": "opaque-not-part-of-the-note"}):
            with self.subTest(signature=bool(signature)):
                self.assertEqual(self.generate([{"text": json.dumps(VALUE), **signature}]), VALUE)

    def test_thoughts_and_signature_only_parts_are_ignored(self):
        self.assertEqual(self.generate([{"text": "not final JSON", "thought": True},
            {"thoughtSignature": "opaque"}, {"text": json.dumps(VALUE), "thoughtSignature": "opaque"}]), VALUE)

    def test_invalid_or_incomplete_output_is_rejected(self):
        for parts, finish, usage in [([{ "text": "{}", "thoughtSignature": "opaque"}], "STOP", 5),
                                    ([{"text": json.dumps(VALUE)}], "MAX_TOKENS", 5),
                                    ([{"text": json.dumps(VALUE)}], "STOP", 8001),
                                    ([{"text": json.dumps(VALUE), "functionCall": {}}], "STOP", 5),
                                    ([{"text": 123, "thoughtSignature": "opaque"}], "STOP", 5)]:
            with self.subTest(parts=parts, finish=finish, usage=usage):
                with self.assertRaises(DomainError) as raised:
                    self.generate(parts, finish=finish, usage=usage)
                self.assertEqual(raised.exception.code, "PROVIDER_SCHEMA_INVALID")

    def test_quota_error_remains_retryable(self):
        with self.assertRaises(DomainError) as raised:
            self.generate([], status=429)
        self.assertEqual(raised.exception.code, "PROVIDER_TRANSIENT")


if __name__ == "__main__":
    unittest.main()
