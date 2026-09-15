"""Pin portable name folding to the same Unicode database as the Core profile."""
import json
import unicodedata
from pathlib import Path

table = {chr(point): chr(point).casefold() for point in range(0x110000)
         if not 0xD800 <= point <= 0xDFFF and chr(point).casefold() != chr(point)}
path = Path(__file__).resolve().parents[1] / "bridge/src/unicode-fold.json"
path.write_text(json.dumps({"unicode_version": unicodedata.unidata_version, "mapping": table}, ensure_ascii=True,
                           separators=(",", ":"))+"\n", encoding="utf-8")
print(f"Pinned {len(table)} Unicode {unicodedata.unidata_version} case-fold entries.")
