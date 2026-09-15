"""Generate portable parser conformance cases from the authoritative Core parser."""
import json
from dataclasses import asdict
from pathlib import Path

from mastermind.fs import name_key
from mastermind.references import parse

names = ["Example", "Example note", "Café", "Étage", "Straße", "İstanbul", "ΟΣ", "Ὀδυσσεύς",
         "Тема", "𐐀𐐁", "😀 note", "constructor", "__proto__", "中文", "ﬃ"]
current = {name_key(name): name for name in names}
history, saturn = ["Old name", "Deleted"], ["root/my file.pdf", "root/folder", "root/中文 文件.pdf"]
texts = [
    ("---\ntags: [main]\nx: '@Example'\n---\n@Example note. @Examplemore user@Example.org\n"
     "\\@Example `@Example`\n```md\n@Example\n```\n<!-- @Example -->\n@Cafe\u0301 @STRASSE [[Example|label]]"),
    "@Old name @chronos: event-123 @unknown: text @saturn: root/my file.pdf",
    "@Deleted @saturn: root/unknown.dat @saturn: root/中文 文件.pdf @saturn: /outside @chronos:no-space",
    "😀 [[folder/Café.md#header|@Example]] ![[Deleted]] \\[[Example]] \\\\@Example",
    "> ```\n> @Example\n> ```\n\n- item\n\n      @Example\n\n@Example",
    "<div>\n@Example\n</div>\n\n@Example <i title='@Example'>visible</i>\n",
    "~~~md\r\n@Example\r\n~~~\r\n@Example\r\n\r\n    @Example\r\n",
    "```\n@Example\n\n@Deleted",
    "---\r\ntitle: '@Example'\r\n...\r\n@Example `unfinished @Deleted",
]
for name in names:
    import unicodedata
    for variant in (name, name.upper(), name.lower(), unicodedata.normalize("NFD", name)):
        for prefix, suffix in (("", ""), ("😀 ", "."), ("𐄀", "𐄀"), ("a", ""), ("_", ""),
                               (" ", "_rest"), (" ", "longer"), ("\\", " "), ("\\\\", " ")):
            texts.append(prefix + "@" + variant + suffix)

cases = [{"text": text, "current": current, "history": history, "saturn": saturn,
          "expected": [asdict(ref) for ref in parse(text, current, history, saturn)]} for text in texts]
path = Path(__file__).resolve().parents[1] / "bridge/tests/portable-cases.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", "utf-8")
print(f"Generated {len(cases)} Core conformance cases")
