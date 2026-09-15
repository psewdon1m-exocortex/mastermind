import io
import json
import stat
import sys
import tarfile
import zipfile

import pytest
from pypdf import PdfWriter

from mastermind.errors import DomainError
from mastermind.extractors import extract


def source(tmp_path, name, data):
    path = tmp_path / "source"
    path.write_bytes(data)
    return extract(path, name)


def zip_source(tmp_path, entries, name="source.zip"):
    path = tmp_path / "source"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for key, value in entries:
            if isinstance(key, str):
                info = zipfile.ZipInfo(key)
                info.filename = key  # Preserve hostile spellings even on Windows.
                info.compress_type = zipfile.ZIP_DEFLATED
            else:
                info = key
            archive.writestr(info, value)
    return extract(path, name)


def test_html_extracts_article_and_metadata_without_scripts_navigation_or_credentials(tmp_path):
    result = source(tmp_path, "page.html", b'''<!doctype html><html><head><title>Document</title>
        <meta name="author" content="Example Author"></head><body><nav>MENU CANARY</nav>
        <main><h1>Main heading</h1><p>Useful facts.</p><script>SECRET SCRIPT</script></main></body></html>''')
    assert result["title"] == "Document" and result["metadata"]["author"] == "Example Author"
    assert "Useful facts" in result["text"] and "CANARY" not in result["text"] and "SCRIPT" not in result["text"]
    assert not result["needs_browser"]


def test_javascript_only_page_requires_browser_stage(tmp_path):
    result = source(tmp_path, "page.html", b"<html><body><div id='app'></div><script src='/app.js'></script></body></html>")
    assert result["needs_browser"] and not result["text"]


def test_ooxml_document_and_text_pdf_fallback(tmp_path):
    result = zip_source(tmp_path, [("word/document.xml", b'<w:document xmlns:w="urn:word"><w:p><w:t>Document facts</w:t></w:p></w:document>')], "note.docx")
    assert result["type"] == "document" and "Document facts" in result["text"]
    document = PdfWriter()
    document.add_blank_page(100, 100)
    data = io.BytesIO()
    document.write(data)
    result = source(tmp_path, "scan.pdf", data.getvalue())
    assert result["type"] == "pdf" and result["needs_media"] and result["metadata"]["pages"] == 1


def test_rtf_unicode_codepage_and_hidden_destinations(tmp_path):
    result = source(tmp_path, "note.rtf", br"{\rtf1\ansi\ansicpg1251 {\fonttbl{\f0 CANARY;}}\u1055?\u1088?\u1080?\u1074?\u1077?\u1090?\par \'ec\'e8\'f0 \u-10179?\u-8704?}")
    assert result["type"] == "document"
    assert "Привет" in result["text"] and "мир" in result["text"] and "😀" in result["text"]
    assert "CANARY" not in result["text"] and "rtf1" not in result["text"]


@pytest.mark.skipif(sys.platform != "linux", reason="The qualified antiword parser runs in the Linux Worker")
def test_actual_legacy_doc_parser(tmp_path):
    from pathlib import Path
    fixture = Path(__file__).parent/"fixtures/documents/legacy.doc"
    result = extract(fixture, "legacy.doc")
    assert result["type"] == "document" and "Legacy document facts." in result["text"]


def test_xlsx_resolves_shared_rich_strings_cells_and_workbook_order(tmp_path):
    result = zip_source(tmp_path, [
        ("xl/workbook.xml", '<workbook xmlns:r="urn:relationships"><sheets><sheet name="First" r:id="b"/><sheet name="Second" r:id="a"/></sheets></workbook>'),
        ("xl/_rels/workbook.xml.rels", '<Relationships><Relationship Id="a" Target="worksheets/sheet1.xml"/><Relationship Id="b" Target="worksheets/sheet10.xml"/><Relationship Id="remote" TargetMode="External" Target="https://example.invalid/"/></Relationships>'),
        ("xl/sharedStrings.xml", '<sst><si><r><t>Revenue </t></r><r><t>facts</t></r></si></sst>'),
        ("xl/worksheets/sheet10.xml", '<worksheet><sheetData><row><c r="A1" t="s"><v>0</v></c><c r="C1"><v>42</v></c><c r="D1" t="b"><v>1</v></c><c r="E1"><f>2+2</f><v>4</v></c><c r="F1"><f>EXTERNAL()</f></c></row></sheetData></worksheet>'),
        ("xl/worksheets/sheet1.xml", '<worksheet><sheetData><row><c r="B2" t="inlineStr"><is><t>Inline facts</t></is></c></row></sheetData></worksheet>'),
    ], "notes.xlsx")
    value = result["text"]
    assert value.index("First") < value.index("Second")
    assert "A1: Revenue facts | C1: 42 | D1: TRUE | E1: 4 | F1: [formula result unavailable]" in value
    assert "B2: Inline facts" in value and "EXTERNAL" not in value


def test_xlsx_rejects_invalid_shared_string_reference(tmp_path):
    with pytest.raises(DomainError, match="shared-string"):
        zip_source(tmp_path, [("xl/workbook.xml", "<workbook/>"),
                             ("xl/worksheets/sheet1.xml", '<worksheet><row><c t="s"><v>9</v></c></row></worksheet>')], "notes.xlsx")


def test_presentation_uses_slide_order_in_relationships(tmp_path):
    result = zip_source(tmp_path, [
        ("ppt/presentation.xml", '<presentation xmlns:r="urn:relationships"><sldIdLst><sldId r:id="b"/><sldId r:id="a"/></sldIdLst></presentation>'),
        ("ppt/_rels/presentation.xml.rels", '<Relationships><Relationship Id="a" Target="slides/slide1.xml"/><Relationship Id="b" Target="slides/slide10.xml"/></Relationships>'),
        ("ppt/slides/slide1.xml", "<slide><t>Last page</t></slide>"),
        ("ppt/slides/slide10.xml", "<slide><t>First page</t></slide>"),
    ], "slides.pptx")
    assert result["text"].index("First page") < result["text"].index("Last page")


def test_archive_excludes_secret_files_and_scrubs_secret_like_values(tmp_path):
    result = zip_source(tmp_path, [("README.md", "Useful source\n"), (".env", "DO NOT SEND"),
        ("credentials.json", '{"password":"CANARY"}'), ("src/app.py", 'api_key = "CANARY"\nprint("safe")'),
        ("private.pem", "PRIVATE KEY CANARY")])
    assert "Useful source" in result["text"] and "safe" in result["text"]
    assert "CANARY" not in json.dumps(result) and "DO NOT SEND" not in json.dumps(result)


@pytest.mark.parametrize("entries", [
    [("../escape", "bad")], [("/absolute", "bad")], [("C:drive", "bad")], [("a\\b", "bad")],
    [("Straße.txt", "one"), ("STRASSE.txt", "two")], [("a.txt", "one"), ("A.txt", "two")],
    [("dir", "file"), ("dir/child", "bad")], [("a/"*17+"deep", "bad")],
    [("bomb.txt", "a"*(2*1024**2))],
])
def test_hostile_archives_are_rejected_before_content_is_emitted(tmp_path, entries):
    with pytest.raises(DomainError) as failure:
        zip_source(tmp_path, entries)
    assert failure.value.code in ("ARCHIVE_UNSAFE", "ARCHIVE_LIMIT")


def test_zip_links_and_tar_hardlinks_rejected(tmp_path):
    link = zipfile.ZipInfo("link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(DomainError):
        zip_source(tmp_path, [(link, "../outside")])
    path = tmp_path / "source"
    with tarfile.open(path, "w") as archive:
        member = tarfile.TarInfo("link")
        member.type, member.linkname = tarfile.LNKTYPE, "/etc/passwd"
        archive.addfile(member)
    with pytest.raises(DomainError):
        extract(path, "source.tar")


def test_output_is_bounded_and_binary_files_fail_explicitly(tmp_path):
    result = source(tmp_path, "large.txt", b"many source facts\n"*50_000)
    assert result["truncated"] and len(result["text"].encode()) <= 512*1024
    with pytest.raises(DomainError) as failure:
        source(tmp_path, "unknown.bin", b"\x00\xff\x11"*100)
    assert failure.value.code == "EXTRACTION_FAILED"


def test_media_sniffing_does_not_trust_a_misleading_filename(tmp_path):
    result = source(tmp_path, "document.txt", b"ID3" + b"\0"*100)
    assert result["type"] == "audio" and result["needs_media"] and result["mime"] == "audio/mpeg"
