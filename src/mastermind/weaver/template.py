"""Versioned Markdown template parser. Substitution never executes or reparses fields."""
import re
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml
from markdown_it import MarkdownIt
from pydantic import BaseModel, ConfigDict, Field

from ..errors import DomainError
from ..extractors import scrub
from ..fs import sha_bytes
from ..references import masked, note_tags

VERSION = "context-indexing.template.v1"
DEFAULT_PATH = "root/templates/example crusher.md"
DEFAULT_TEMPLATE = """# {{title}}

## Кратко

{{crusher.summary}}

## Основной материал

{{crusher.body}}

## Источник

{{crusher.sources}}

## Связи

{{crusher.links}}
"""
SLOT = re.compile(r"\{\{([^{}\n]+)\}\}")
ALLOWED = {"title", "date", "time", "crusher.summary", "crusher.body", "crusher.sources", "crusher.links"}


class GeneratedFields(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=16000)
    body: str = Field(min_length=1, max_length=100000)


def fail(code="TEMPLATE_INVALID", message="Select a valid Crusher Markdown template."):
    raise DomainError(code, message, 422)


def parse(text):
    if not isinstance(text, str) or len(text.encode()) > 64*1024 or "\0" in text:
        fail()
    if scrub(text) != text or "mastermind:crusher" in text:
        fail("TEMPLATE_UNSAFE", "A template cannot contain secrets, structural tags or system metadata.")
    plain = masked(text)
    slots = list(SLOT.finditer(text))
    counts = Counter(match[1] for match in slots)
    if set(counts)-ALLOWED or any(count != 1 for count in counts.values()) \
            or not {"crusher.body", "crusher.links"} <= counts.keys():
        fail("TEMPLATE_SLOTS", "Use each supported placeholder once, including crusher.body and crusher.links.")
    # The reference masker preserves offsets while removing fences/frontmatter.
    if any(SLOT.match(plain, match.start()) is None for match in slots):
        fail("TEMPLATE_SLOTS", "Place placeholders outside code blocks and frontmatter.")
    literal = SLOT.sub("", text)
    exposed = masked(literal)
    tokens = MarkdownIt("commonmark", {"html": True}).parse(literal)
    if any(t.type in {"html_block", "html_inline", "link_open", "image"}
           for token in tokens for t in [token, *(token.children or [])]):
        fail("TEMPLATE_REFERENCES", "Templates cannot contain executable HTML or unapproved resource links.")
    if re.search(r"\[\[|(?<![\w.\-])@[^\s]|<[^>]+>|!\[|https?://|www\.", exposed, re.IGNORECASE) \
            or "<%" in literal or "{%" in literal:
        fail("TEMPLATE_REFERENCES", "Use the sources and links placeholders for resource references.")
    if re.match(r"---\r?\n", text):
        front = re.match(r"---\r?\n([\s\S]*?)\r?\n(?:---|\.\.\.)(?:\r?\n|$)", text)
        if not front:
            fail()
        frontmatter = front[1]
        try:
            if any(isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken))
                   for token in yaml.scan(frontmatter)):
                fail("TEMPLATE_METADATA", "Frontmatter cannot contain YAML aliases.")
            metadata = yaml.safe_load(frontmatter)
        except (yaml.YAMLError, RecursionError):
            fail()
        if not isinstance(metadata, dict) or len(metadata) > 32 or any(
                not isinstance(key, str) or not isinstance(value, (str, int, float, bool, list, type(None)))
                for key, value in metadata.items()):
            fail("TEMPLATE_METADATA", "Use a bounded, static frontmatter mapping.")
        if re.search(r"\[\[|(?<!\w)@|https?://|\{\{", frontmatter, re.IGNORECASE):
            fail("TEMPLATE_METADATA", "Frontmatter cannot inject references or placeholders.")
    if set(note_tags(text)) & {"main", "key"}:
        fail("TEMPLATE_UNSAFE", "A template cannot contain structural tags.")
    return {"version": VERSION, "text": text, "sha256": sha_bytes(text.encode()), "slots": sorted(counts)}


def render(snapshot, fields, *, sources, link, timestamp, timezone="UTC"):
    parsed = parse(snapshot["text"])
    if parsed["sha256"] != snapshot.get("sha256") or snapshot.get("version") != VERSION:
        fail("TEMPLATE_CHANGED", "The saved template snapshot failed integrity.")
    moment = datetime.fromtimestamp(timestamp, ZoneInfo(timezone))
    title = re.sub(r"([\\`*_{}\[\]()#+.!<>|])", r"\\\1", fields["title"])
    values = {"title": title, "date": moment.strftime("%Y-%m-%d"), "time": moment.strftime("%H:%M"),
              "crusher.summary": fields["summary"], "crusher.body": fields["body"],
              "crusher.sources": sources, "crusher.links": link}
    return SLOT.sub(lambda match: values[match[1]], parsed["text"]).rstrip()+"\n"
