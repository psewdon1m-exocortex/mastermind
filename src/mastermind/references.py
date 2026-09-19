"""Markdown-aware references; byte offsets never rely on case-folded text length."""
import re
import unicodedata
from dataclasses import dataclass

import yaml
from markdown_it import MarkdownIt

from .fs import name_key

MD = MarkdownIt("commonmark", {"html": True})
WIKI = re.compile(r"(!?)\[\[([^\]\r\n]+)\]\]")
EXTERNAL = re.compile(r"@([a-z]+):[ \t]+([^\s<>]+)")


@dataclass(frozen=True)
class Reference:
    start: int
    end: int
    kind: str
    target: str
    display: str
    exists: bool


def excluded_spans(text):
    spans = []
    front = re.match(r"---\r?\n[\s\S]*?\r?\n(?:---|\.\.\.)(?:\r?\n|$)", text)
    if front:
        spans.append((0, front.end()))
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    for token in MD.parse(text):
        if token.type in ("fence", "code_block", "html_block") and token.map:
            spans.append((offsets[token.map[0]], offsets[min(token.map[1], len(offsets)-1)]))
    spans.extend((m.start(), m.end()) for m in re.finditer(r"<!--[\s\S]*?(?:-->|$)", text))
    tick = chr(96)
    for match in re.finditer("(?<!" + tick + ")(" + tick + "+)(?!" + tick + ")", text):
        if any(a <= match.start() < b for a, b in spans):
            continue
        closing = re.search("(?<!" + tick + ")" + re.escape(match.group()) + "(?!" + tick + ")",
                            text[match.end():])
        if closing:
            spans.append((match.start(), match.end() + closing.end()))
    spans.extend((m.start(), m.end()) for m in re.finditer(r"<[^>\n]+>", text))
    return spans


def masked(text):
    result = list(text)
    for a, b in excluded_spans(text):
        for i in range(a, b):
            if result[i] != "\n":
                result[i] = "\0"
    return "".join(result)


def escaped(text, start):
    count = 0
    while start > 0 and text[start-1] == "\\":
        count += 1
        start -= 1
    return count % 2 == 1


def left_boundary(text, position):
    if position == 0:
        return True
    c = text[position-1]
    return c.isspace() or (unicodedata.category(c).startswith("P") and c not in "._-\\")


def right_boundary(text, position):
    if position == len(text):
        return True
    c = text[position]
    return c.isspace() or (unicodedata.category(c).startswith("P") and c != "_")


def match_name(text, start, display):
    wanted = name_key(display)
    for end in range(start+1, min(len(text), start + len(wanted)*3 + 8) + 1):
        part = name_key(text[start:end])
        if part == wanted and right_boundary(text, end):
            return end
        if len(part) > len(wanted)+2 or "\0" in part or "\n" in part:
            break
    return None


def prepare_names(current, history=()):
    names = {name_key(n): n for n in history}
    names.update(current)
    return sorted(names.values(), key=lambda n: len(name_key(n)), reverse=True)


def parse(text: str, current: dict[str, str], history=(), saturn_paths=(), *, prepared_names=None):
    visible = masked(text)
    found, occupied = [], []
    for match in WIKI.finditer(visible):
        if escaped(text, match.start()):
            continue
        raw = match[2].split("|", 1)[0].split("#", 1)[0].split("^", 1)[0].strip()
        target = raw.rsplit("/", 1)[-1]
        if target.lower().endswith(".md"):
            target = target[:-3]
        if not target:
            continue
        found.append(Reference(match.start(), match.end(), "internal", name_key(target), target,
                               name_key(target) in current))
        occupied.append((match.start(), match.end()))
    if "@" not in visible:
        return sorted(found, key=lambda ref: ref.start)
    ordered = prepare_names(current, history) if prepared_names is None else prepared_names
    for match in re.finditer("@", visible):
        start = match.start()
        if escaped(text, start) or not left_boundary(text, start) or any(a <= start < b for a, b in occupied):
            continue
        namespace = re.match(r"@([a-z]+):", visible[start:])
        if namespace:
            if namespace[1] not in ("chronos", "saturn"):
                continue
            ext = EXTERNAL.match(visible, start)
            if not ext:
                continue
            target, end = ext[2], ext.end()
            if ext[1] == "saturn":
                beginning = ext.start(2)
                for path in sorted(saturn_paths, key=len, reverse=True):
                    if visible.startswith(path, beginning) and right_boundary(visible, beginning+len(path)):
                        target, end = path, beginning + len(path)
                        break
                if target != "root" and not target.startswith("root/"):
                    continue
            found.append(Reference(start, end, ext[1], target, text[start:end],
                                   ext[1] == "chronos" or target in saturn_paths))
            continue
        for display in ordered:
            if unicodedata.normalize("NFD", visible[start+1:start+2]).casefold()[:1] != \
                    unicodedata.normalize("NFD", display[:1]).casefold()[:1]:
                continue
            end = match_name(visible, start+1, display)
            if end is not None:
                found.append(Reference(start, end, "internal", name_key(display), display,
                                       name_key(display) in current))
                break
    return sorted(found, key=lambda ref: ref.start)


def note_tags(text):
    tags = set(re.findall(r"(?<![\w/])#([\w/-]+)", masked(text)))
    match = re.match(r"---\r?\n([\s\S]*?)\r?\n(?:---|\.\.\.)(?:\r?\n|$)", text)
    if match:
        try:
            value = yaml.safe_load(match[1]) or {}
            entries = value.get("tags", []) if isinstance(value, dict) else []
            if isinstance(entries, str):
                entries = re.split(r"[,\s]+", entries)
            if isinstance(entries, list):
                tags.update(str(tag).lstrip("#") for tag in entries if isinstance(tag, str))
        except yaml.YAMLError:
            pass
    return sorted(tags)
