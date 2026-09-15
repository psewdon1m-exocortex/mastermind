"""Lossless, server-held public projection. This module has no Vault or resolver access.

A block containing a forbidden construct is immutable as a whole. This deliberately
keeps ambiguous Markdown (nested lists, fences and reference definitions) out of the
editable surface. Unrelated blocks remain editable. No source bytes are normalized.
"""
import html
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import unquote

from markdown_it import MarkdownIt

from .errors import DomainError

PARSER = MarkdownIt("commonmark", {"html": True, "linkify": False, "maxNesting": 32})
FORBIDDEN = re.compile(r"@|\[\[|\]\]|<|(?:[a-z][a-z\d+.-]{1,31}:)|www\.|"
                       r"!?\[[^\n]*\](?:\s*\(|\s*\[)|^ {0,3}\[[^\n]+\]:", re.IGNORECASE | re.MULTILINE)
SAFE_TAGS = frozenset(["p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "strong", "em", "s", "code", "pre", "blockquote", "ul", "ol", "li"])
MARKER = "MMProtectedFragmentBoundary"


def normalized(value):
    for _ in range(6):
        decoded = unicodedata.normalize("NFKC", html.unescape(unquote(value)))
        decoded = re.sub(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\]\\^_`{|}~])", r"\1", decoded)
        decoded = "".join(c for c in decoded if unicodedata.category(c) != "Cf")
        if decoded == value:
            return decoded
        value = decoded
    # Deeply nested encodings are not useful editable prose. Fail closed.
    if html.unescape(unquote(value)) != value:
        return "@"
    return value


def forbidden(value):
    value = normalized(value)
    if FORBIDDEN.search(value):
        return True
    return any(child.type in ("link_open", "image", "html_inline")
               for token in PARSER.parse(value) for child in (token.children or ()))


def partition(source):
    lines = re.findall(r".*?(?:\r\n|\r|\n|$)", source, re.DOTALL)[:-1]
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    spans = []
    if lines and lines[0].lstrip("\ufeff").rstrip("\r\n") == "---":
        end = next((i+1 for i, line in enumerate(lines[1:], 1)
                    if line.rstrip("\r\n") in ("---", "...")), len(lines))
        spans.append((0, offsets[end]))
    tokens = PARSER.parse(source)
    for token in tokens:
        if token.map and any(child.type in ("link_open", "image", "html_inline") for child in (token.children or ())):
            spans.append(tuple(offsets[index] for index in token.map))
    for token in tokens:
        if token.level == 0 and token.map:
            start, end = (offsets[index] for index in token.map)
            if forbidden(source[start:end]) or token.type == "html_block" \
                    or any(left < end and right > start for left, right in spans):
                spans.append((start, end))
    # Reference definitions are consumed into Markdown's environment, not tokens.
    for index, line in enumerate(lines):
        if forbidden(line):
            spans.append((offsets[index], offsets[index+1]))
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    values, fragments, cursor = [], [], 0
    for start, end in merged:
        values.append(source[cursor:start])
        fragments.append(source[start:end])
        cursor = end
    values.append(source[cursor:])
    return {"values": values, "fragments": fragments}


def join(values, fragments):
    return "".join(value + (fragments[i] if i < len(fragments) else "") for i, value in enumerate(values))


def contexts(values, fragments, marker=MARKER):
    """Preserve the Markdown container of every protected block across an edit."""
    replacements = [f"{marker}{i}End" + ("\n" if part.endswith(("\r", "\n")) else "")
                    for i, part in enumerate(fragments)]
    result, stack = {}, []

    def visit(tokens, parents):
        local = list(parents)
        for token in tokens:
            if token.nesting == -1:
                if local:
                    local.pop()
                continue
            shape = (token.type, token.tag, token.markup, token.info)
            if token.children:
                visit(token.children, local + [shape])
            else:
                for match in re.finditer(marker + r"(\d+)End", token.content):
                    key = int(match[1])
                    if key in result:
                        raise DomainError("REFERENCE_NOT_ALLOWED", "Protected content context is invalid.", 422)
                    result[key] = local + [shape]
            if token.nesting == 1:
                local.append(shape)

    visit(PARSER.parse(join(values, replacements)), stack)
    return result


def reconstruct(record, values, limit):
    original, fragments = record["values"], record["fragments"]
    if not isinstance(values, list) or len(values) != len(original) or any(not isinstance(v, str) for v in values):
        raise DomainError("INVALID_PROJECTION", "Editable segments do not match this projection.", 422)
    if sum(len(value.encode("utf-8")) for value in values + fragments) > limit:
        raise DomainError("SIZE_LIMIT", "Shared note exceeds its size limit.", 413)
    if any(forbidden(value) for value in values):
        raise DomainError("REFERENCE_NOT_ALLOWED", "References and resources cannot be added through Shared.", 422)
    result = join(values, fragments)
    rebuilt = partition(result)
    marker = MARKER
    while any(marker in value for value in original + values):
        marker += "X"
    if rebuilt["fragments"] != fragments \
            or contexts(values, fragments, marker) != contexts(original, fragments, marker):
        raise DomainError("REFERENCE_NOT_ALLOWED", "Protected content or its Markdown context cannot change.", 422)
    return result


class Allowlist(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []

    def handle_starttag(self, tag, attrs):
        if tag in SAFE_TAGS:
            self.output.append("<" + tag + ">")

    def handle_endtag(self, tag):
        if tag in SAFE_TAGS and tag not in ("br", "hr"):
            self.output.append("</" + tag + ">")

    def handle_data(self, data):
        self.output.append(html.escape(data))


def public(record):
    # Each safe text segment is rendered independently. Protected source never
    # enters the public Markdown renderer, HTML response, or browser state.
    parts, rendered = [], []
    for index, value in enumerate(record["values"]):
        parts.append({"kind": "text", "value": value})
        cleaner = Allowlist()
        cleaner.feed(PARSER.render(value))
        rendered.append("".join(cleaner.output))
        if index < len(record["fragments"]):
            parts.append({"kind": "protected", "label": "Hidden content"})
            rendered.append('<p class="protected">Hidden content</p>')
    return {"segments": parts, "html": "".join(rendered)}
