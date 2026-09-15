"""Small generated document/media/Saturn inputs for the full local Crusher probe."""
import json
import shutil
import sys
import wave
import zipfile
from pathlib import Path

from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from probe_integrations import FIXTURE, client

directory = FIXTURE / "crusher"
directory.mkdir(exist_ok=True)
shutil.copyfile(ROOT / "tests/fixtures/documents/legacy.doc", directory / "legacy.doc")
(directory / "source.rtf").write_bytes(br"{\rtf1\ansi Knowledge architecture from RTF.\par Structured source facts.}")
with zipfile.ZipFile(directory / "source.xlsx", "w", zipfile.ZIP_DEFLATED) as archive:
    archive.writestr("xl/workbook.xml", '<workbook xmlns:r="urn:relationships"><sheets><sheet name="Facts" r:id="a"/></sheets></workbook>')
    archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships><Relationship Id="a" Target="worksheets/sheet1.xml"/></Relationships>')
    archive.writestr("xl/sharedStrings.xml", '<sst><si><t>Knowledge architecture from a spreadsheet</t></si></sst>')
    archive.writestr("xl/worksheets/sheet1.xml", '<worksheet><sheetData><row><c r="A1" t="s"><v>0</v></c><c r="B1"><v>42</v></c></row></sheetData></worksheet>')
with zipfile.ZipFile(directory / "source.docx", "w", zipfile.ZIP_DEFLATED) as archive:
    archive.writestr("word/document.xml", '<w:document xmlns:w="urn:word"><w:p><w:t>Knowledge architecture from a generated office document.</w:t></w:p></w:document>')
pdf = PdfWriter()
pdf.add_blank_page(200, 200)
with (directory / "scan.pdf").open("wb") as target:
    pdf.write(target)
with wave.open(str(directory / "source.wav"), "wb") as target:
    target.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
    target.writeframes(b"\0"*16000)
credentials = json.loads((FIXTURE / "enrollment.json").read_text())
saturn = client("saturn")
headers = {"Authorization": "Bearer " + credentials["mirrorToken"], "Content-Type": "application/octet-stream"}
route = "/dav/mastermind/Crusher fixture.txt"
previous = saturn.head(route, headers=headers)
headers["If-Match" if previous.status_code == 200 else "If-None-Match"] = previous.headers["etag"] if previous.status_code == 200 else "*"
result = saturn.put(route, headers=headers, content=b"Knowledge architecture from the selected Saturn resource.")
assert result.status_code in (201, 204), f"Saturn fixture HTTP {result.status_code}"
print("PASS: generated office/PDF/audio fixtures and actual Saturn source are ready.")
