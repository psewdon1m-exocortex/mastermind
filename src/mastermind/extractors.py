"""Deterministic, network-free source extraction; run inside the Worker sandbox."""
import json
import os
import posixpath
import re
import selectors
import stat
import subprocess
import tarfile
import time
import unicodedata
import zipfile
from pathlib import PurePosixPath

from .errors import DomainError

MAX_TEXT = 512*1024
SECRET_NAMES = re.compile(r"(^|/)(?:\.git|\.env(?:\..*)?|id_rsa|id_ed25519|credentials?(?:\..*)?|"
                          r"secrets?(?:\..*)?|tokens?(?:\..*)?|\.npmrc|\.pypirc)(/|$)|\.(?:pem|key|p12|pfx)$", re.IGNORECASE)
PRIVATE_KEY = re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?(?:-----END [^-]*PRIVATE KEY-----|$)")
KEY_VALUE = re.compile(r"(?im)^(\s*(?:(?:const|let|var|export)\s+)?['\"]?(?:api[_-]?key|password|passwd|token|secret|authorization|access[_-]?key)['\"]?\s*[:=]).*$")


def scrub(text):
    text = PRIVATE_KEY.sub("[private key omitted]", text)
    text = KEY_VALUE.sub(r"\1 [secret value omitted]", text)
    text = re.sub(r'''(?i)(["'](?:api[_-]?key|password|passwd|token|secret|authorization|access[_-]?key)["']\s*:\s*)"(?:\\.|[^"\\])*"''',
                  r'\1"[secret value omitted]"', text)
    text = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9_./+=-]+", "Bearer [omitted]", text)
    text = re.sub(r"\b(?:AIza[A-Za-z0-9_-]{35}|sk-[A-Za-z0-9_-]{16,})\b", "[provider key omitted]", text)
    return text


class Text:
    def __init__(self, limit=MAX_TEXT):
        self.limit, self.size, self.parts, self.truncated = limit, 0, [], False

    def add(self, value):
        data = scrub(value).encode("utf-8")
        remaining = self.limit-self.size
        if len(data) > remaining:
            self.truncated = True
        data = data[:remaining]
        value = data.decode("utf-8", errors="ignore")
        self.parts.append(value)
        self.size += len(value.encode("utf-8"))

    def value(self):
        return "".join(self.parts)


def archive_path(name, seen, *, directory=False):
    name = name.rstrip("/") if directory else name
    path = PurePosixPath(name)
    if not name or "\\" in name or ":" in name or name.startswith("/") or len(name.encode("utf-8")) > 4096 \
            or len(name.split("/")) > 16 or any(part in ("", ".", "..") or part.endswith((" ", "."))
                                             for part in name.split("/")) or any(ord(c) < 32 for c in name):
        raise DomainError("ARCHIVE_UNSAFE", "The source archive contains an unsafe path.", 422)
    key = unicodedata.normalize("NFC", name).casefold()
    if key in seen or any(seen.get(unicodedata.normalize("NFC", str(parent)).casefold()) == "file"
                          for parent in path.parents if str(parent) != ".") \
            or not directory and any(previous.startswith(key+"/") for previous in seen):
        raise DomainError("ARCHIVE_UNSAFE", "The source archive has colliding paths.", 422)
    seen[key] = "directory" if directory else "file"
    return name


def zip_inventory(archive):
    entries, seen, total = archive.infolist(), {}, 0
    if len(entries) > 10_000:
        raise DomainError("ARCHIVE_LIMIT", "The source archive has too many entries.", 413)
    for item in entries:
        # ZipInfo normalizes Windows separators and truncates NULs in filename;
        # validate the original central-directory spelling before either occurs.
        original = item.orig_filename
        archive_path(original, seen, directory=item.is_dir())
        if original != item.filename:
            raise DomainError("ARCHIVE_UNSAFE", "The archive contains a non-canonical path spelling.", 422)
        mode = stat.S_IFMT(item.external_attr >> 16)
        if mode not in (0, stat.S_IFREG, stat.S_IFDIR) or item.flag_bits & 1:
            raise DomainError("ARCHIVE_UNSAFE", "Special or encrypted source archive entries are unsupported.", 422)
        if item.file_size > 2*1024**3 or item.file_size > max(item.compress_size, 1)*1000:
            raise DomainError("ARCHIVE_LIMIT", "The source archive exceeds its expansion limit.", 413)
        total += item.file_size
        if total > 8*1024**3:
            raise DomainError("ARCHIVE_LIMIT", "The source archive exceeds 8 GiB of expanded data.", 413)
    return entries


def read_member(archive, item, limit=8*1024**2):
    if item.file_size > limit:
        raise DomainError("EXTRACTION_LIMIT", "A document component exceeds its extraction limit.", 413)
    with archive.open(item) as stream:
        data = stream.read(limit+1)
        if len(data) != item.file_size or len(data) > limit:
            raise DomainError("SOURCE_INTEGRITY", "The archive member size is inconsistent.", 422)
        return data


def decode(data):
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    if b"\0" in data[:8192]:
        raise UnicodeError("Binary document")
    return data.decode("utf-8-sig")


def html_document(data):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(data, "html.parser")
    title = soup.title.get_text(" ", strip=True)[:300] if soup.title else ""
    metadata = {}
    for key in ("author", "date", "article:published_time"):
        element = soup.find("meta", attrs={"name": key}) or soup.find("meta", attrs={"property": key})
        if element and isinstance(element.get("content"), str):
            metadata[key] = scrub(element["content"])[:256]
    script_count = len(soup.find_all("script"))
    for element in soup.find_all(["script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg", "iframe"]):
        element.decompose()
    article = soup.find("article") or soup.find("main")
    root = article or soup.body or soup
    text = root.get_text("\n", strip=True)
    return title, text, metadata, script_count > 0 and (len(text.strip()) < 20 or article is None and len(text.strip()) < 120)


def xml_text(data):
    from defusedxml import ElementTree
    root = ElementTree.fromstring(data)
    return "\n".join(value.strip() for value in root.itertext() if value.strip())


def relationship_order(archive, names, document, relationships, element):
    """Resolve package-local relationships in actual workbook/presentation order."""
    from defusedxml import ElementTree
    if relationships not in names:
        return []
    root = ElementTree.fromstring(read_member(archive, names[relationships]))
    targets = {}
    for item in root:
        target = item.get("Target", "")
        if item.get("TargetMode") == "External":
            continue
        if not target or "\\" in target or ":" in target or "?" in target or "#" in target:
            raise DomainError("DOCUMENT_UNSAFE", "The document contains an invalid package relationship.", 422)
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(document), target)) \
            if not target.startswith("/") else target.lstrip("/")
        if resolved.startswith("../") or resolved not in names:
            continue
        targets[item.get("Id")] = resolved
    root = ElementTree.fromstring(read_member(archive, names[document]))
    result = []
    for item in root.iter():
        if item.tag.rsplit("}", 1)[-1] == element:
            identifier = next((v for k, v in item.attrib.items() if k.endswith("}id")), None)
            if identifier in targets:
                result.append((targets[identifier], item.get("name", "")))
    return result


def extract_workbook(archive, names, text):
    from defusedxml import ElementTree
    shared = []
    if "xl/sharedStrings.xml" in names:
        root = ElementTree.fromstring(read_member(archive, names["xl/sharedStrings.xml"]))
        shared = ["".join(node.text or "" for node in item.iter() if node.tag.rsplit("}", 1)[-1] == "t")
                  for item in root if item.tag.rsplit("}", 1)[-1] == "si"]
    sheets = relationship_order(archive, names, "xl/workbook.xml", "xl/_rels/workbook.xml.rels", "sheet")
    if not sheets:
        sheets = [(name, name) for name in sorted(names, key=natural_order)
                  if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)]
    for name, label in sheets:
        if text.size >= text.limit:
            text.truncated = True
            break
        root = ElementTree.fromstring(read_member(archive, names[name]))
        text.add(f"\n--- Sheet: {label or name} ---\n")
        for row in root.iter():
            if row.tag.rsplit("}", 1)[-1] != "row":
                continue
            cells = []
            for cell in row:
                if cell.tag.rsplit("}", 1)[-1] != "c":
                    continue
                kind = cell.get("t", "n")
                value = next((node.text or "" for node in cell if node.tag.rsplit("}", 1)[-1] == "v"), "")
                if kind == "s":
                    if not value.isdecimal() or len(value) > 8 or int(value) >= len(shared):
                        raise DomainError("DOCUMENT_CORRUPT", "A spreadsheet cell has an invalid shared-string reference.", 422)
                    value = shared[int(value)]
                elif kind == "inlineStr":
                    value = "".join(node.text or "" for node in cell.iter() if node.tag.rsplit("}", 1)[-1] == "t")
                elif kind == "b":
                    value = "TRUE" if value == "1" else "FALSE" if value == "0" else value
                if not value and any(node.tag.rsplit("}", 1)[-1] == "f" for node in cell):
                    value = "[formula result unavailable]"
                if value:
                    cells.append(f"{cell.get('r', '?')}: {value}")
            text.add(" | ".join(cells) + "\n")
            if text.size >= text.limit:
                text.truncated = True
                break


def natural_order(name):
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name))


def extract_doc(path, text):
    # Invoked inside the existing parser sandbox. Bounded output and wall time;
    # antiword cannot reach network, credentials or other jobs and runs no macros.
    process = subprocess.Popen(["antiword", "-m", "UTF-8.txt", str(path.resolve())],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    deadline, collected = time.monotonic()+30, bytearray()
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                if time.monotonic() >= deadline:
                    raise DomainError("EXTRACTION_TIMEOUT", "The document parser exceeded its deadline.", 422)
                if not selector.select(min(0.25, max(0, deadline-time.monotonic()))):
                    continue
                chunk = os.read(process.stdout.fileno(), min(65536, MAX_TEXT+4-len(collected)))
                if not chunk:
                    if process.wait(timeout=max(0.01, deadline-time.monotonic())):
                        raise DomainError("EXTRACTION_FAILED", "The legacy document is corrupt, encrypted or unsupported.", 422)
                    break
                collected.extend(chunk)
                if len(collected) >= MAX_TEXT+4:
                    text.truncated = True
                    break
        text.add(collected.decode("utf-8", errors="replace"))
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        process.stdout.close()


def extract_zip(path, text):
    with zipfile.ZipFile(path) as archive:
        entries = zip_inventory(archive)
        names = {entry.filename: entry for entry in entries}
        document = "word/document.xml" in names or "content.xml" in names or "ppt/presentation.xml" in names \
            or "xl/workbook.xml" in names
        if document:
            if "xl/workbook.xml" in names:
                extract_workbook(archive, names, text)
                return "document"
            slides = relationship_order(archive, names, "ppt/presentation.xml", "ppt/_rels/presentation.xml.rels", "sldId") \
                if "ppt/presentation.xml" in names else []
            selected = [names[name] for name, _ in slides] if slides else sorted(
                (entry for entry in entries if entry.filename in ("word/document.xml", "content.xml")
                 or re.fullmatch(r"ppt/slides/slide\d+\.xml", entry.filename)),
                key=lambda entry: natural_order(entry.filename))
            for entry in selected:
                if text.size >= text.limit:
                    text.truncated = True
                    break
                text.add("\n" + xml_text(read_member(archive, entry)) + "\n")
            return "document"
        selected = sorted((entry for entry in entries if not entry.is_dir() and not SECRET_NAMES.search(entry.filename)),
                          key=lambda entry: (not bool(re.search(r"(^|/)(?:readme|docs?)(?:[/.]|$)", entry.filename, re.IGNORECASE)),
                                             entry.filename.count("/"), entry.filename))
        for entry in selected:
            if text.size >= text.limit:
                text.truncated = True
                break
            if entry.file_size > 8*1024**2:
                continue
            try:
                content = decode(read_member(archive, entry))
            except UnicodeError:
                continue
            text.add("\n--- " + entry.filename + " ---\n" + content + "\n")
        return "archive"


def extract_tar(path, text):
    seen, count, expanded = {}, 0, 0
    compressed = path.stat().st_size
    # Stream twice: first validate every entry, then read selected ordinary files.
    with tarfile.open(path, "r|*") as archive:
        for entry in archive:
            count += 1
            if count > 10_000 or not (entry.isfile() or entry.isdir()):
                raise DomainError("ARCHIVE_UNSAFE", "The archive contains special entries or too many members.", 422)
            archive_path(entry.name, seen, directory=entry.isdir())
            expanded += entry.size
            if entry.size > 2*1024**3 or expanded > 8*1024**3 or expanded > max(1, compressed)*1000:
                raise DomainError("ARCHIVE_LIMIT", "The source archive exceeds its expansion limit.", 413)
    with tarfile.open(path, "r|*") as archive:
        for entry in archive:
            if text.size >= text.limit:
                text.truncated = True
                break
            if not entry.isfile() or entry.size > 8*1024**2 or SECRET_NAMES.search(entry.name):
                continue
            with archive.extractfile(entry) as stream:
                data = stream.read(entry.size+1)
            if len(data) != entry.size:
                raise DomainError("SOURCE_INTEGRITY", "The archive member ended early.", 422)
            try:
                text.add("\n--- " + entry.name + " ---\n" + decode(data) + "\n")
            except UnicodeError:
                continue


def extract(path, name, mime="application/octet-stream"):
    text, title, metadata = Text(), PurePosixPath(name).stem[:300], {}
    with path.open("rb") as source:
        prefix = source.read(8192)
    result = {"schema": "mastermind.extraction.v1", "needs_media": False, "needs_browser": False}
    suffix = PurePosixPath(name).suffix.lower()
    try:
        if prefix.startswith(b"%PDF-"):
            from pypdf import PdfReader
            reader = PdfReader(path)
            if reader.is_encrypted:
                raise DomainError("SOURCE_ENCRYPTED", "Password-protected source PDFs are unsupported.", 422)
            metadata["pages"] = len(reader.pages)
            if len(reader.pages) > 10000:
                raise DomainError("EXTRACTION_LIMIT", "The PDF page count exceeds its limit.", 413)
            title = str((reader.metadata or {}).get("/Title", title))[:300]
            for number, page in enumerate(reader.pages, 1):
                if text.size >= text.limit:
                    text.truncated = True
                    break
                value = page.extract_text() or ""
                if value.strip():
                    text.add(f"\n--- Page {number} ---\n" + value + "\n")
            result.update(type="pdf", mime="application/pdf", needs_media=not text.value().strip())
        elif prefix.startswith(b"PK\x03\x04"):
            result.update(type=extract_zip(path, text), mime="application/zip")
        elif prefix.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1") and suffix == ".doc":
            extract_doc(path, text)
            result.update(type="document", mime="application/msword")
        elif prefix.lstrip().startswith(b"{\\rtf"):
            from striprtf.striprtf import rtf_to_text
            with path.open("rb") as source:
                data = source.read(8*1024**2+1)
            if len(data) > 8*1024**2:
                raise DomainError("EXTRACTION_LIMIT", "The RTF document exceeds its extraction limit.", 413)
            value = rtf_to_text(data.decode("latin-1"), errors="strict")
            # RTF Unicode escapes may encode a valid UTF-16 surrogate pair.
            text.add(value.encode("utf-16", errors="surrogatepass").decode("utf-16", errors="replace"))
            result.update(type="document", mime="application/rtf")
        elif prefix.startswith(b"\x1f\x8b") or suffix in (".tar", ".tgz"):
            extract_tar(path, text)
            result.update(type="archive", mime="application/x-tar")
        elif prefix.startswith((b"ID3", b"fLaC", b"OggS", b"\x1a\x45\xdf\xa3")) or prefix[4:8] == b"ftyp" \
                or prefix.startswith(b"RIFF") and prefix[8:12] in (b"WAVE", b"AVI ") \
                or prefix[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
            media = "video/mp4" if prefix[4:8] == b"ftyp" else "audio/mpeg" if prefix.startswith(b"ID3") or prefix[:1] == b"\xff" \
                else "audio/flac" if prefix.startswith(b"fLaC") else "audio/ogg" if prefix.startswith(b"OggS") \
                else "audio/wav" if prefix[8:12] == b"WAVE" else "video/webm" if prefix.startswith(b"\x1a") else "video/x-msvideo"
            result.update(type="video" if media.startswith("video/") else "audio", mime=media, needs_media=True)
        else:
            with path.open("rb") as source:
                data = source.read(8*1024**2+1)
            if mime == "text/html" or suffix in (".html", ".htm") or re.match(br"\s*(?:<!doctype html|<html|<head|<body)", prefix, re.IGNORECASE):
                title, content, metadata, browser = html_document(data[:8*1024**2])
                text.add(content)
                result.update(type="webpage", mime="text/html", needs_browser=browser)
            else:
                text.add(decode(data[:8*1024**2]))
                result.update(type="text", mime="text/plain")
            text.truncated |= len(data) > 8*1024**2
        if not text.value().strip() and not result["needs_media"] and not result["needs_browser"]:
            raise DomainError("SOURCE_EMPTY", "No supported readable content was found in the source.", 422)
        return {**result, "title": scrub(title), "metadata": metadata, "text": text.value(), "truncated": text.truncated}
    except (OSError, ValueError, UnicodeError, zipfile.BadZipFile, tarfile.TarError):
        raise DomainError("EXTRACTION_FAILED", "The source is corrupt or uses an unsupported format.", 422) from None


def main():
    import sys
    from pathlib import Path
    # Fixed private filenames are provided by the Worker, never by source content.
    plan = json.loads(Path(sys.argv[1]).read_text("utf-8"))
    try:
        result = extract(Path(plan["path"]), plan["name"], plan["mime"])
    except DomainError as error:
        result = {"error": {"code": error.code, "message": str(error)}}
    Path(sys.argv[2]).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
