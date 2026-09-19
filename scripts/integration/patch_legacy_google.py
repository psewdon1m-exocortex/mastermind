"""Patch the deployed pre-Wyvern adapter without replacing in-progress sources.

Input is a copy of gemini.py from the exact running Core image, never a secret.
The current Wyvern source already consumes normalized JSON rather than these
native Google parts. Remove this deployment repair after the Wyvern cutover.
"""
import sys
from pathlib import Path

target = Path(sys.argv[1])
source = target.read_text(encoding="utf-8")
before = 'content = "".join(item["text"] for item in fragments if not item.get("thought") and set(item) <= {"text", "thought"})'
after = '''# Stateless requests consume final text, not Google's opaque thought signature.
            content = "".join(item["text"] for item in fragments
                if isinstance(item, dict) and isinstance(item.get("text"), str)
                and not item.get("thought") and set(item) <= {"text", "thought", "thoughtSignature"})'''
if source.count(before) != 1:
    raise SystemExit("Expected exactly one legacy parser; do not patch another version.")
source = source.replace(before, after)
prompt = 'embedded resources or references; Core adds verified branch links after validation."""'
if source.count(prompt) != 1:
    raise SystemExit("Expected the legacy Markdown prompt once.")
source = source.replace(prompt, '''embedded resources or references; Core adds verified branch links after validation.
In the markdown string, separate headings, paragraphs and lists with actual newline
characters. Do not double-encode newlines into literal backslash-n text."""''')
target.write_text(source, encoding="utf-8", newline="\n")
print("PASS: legacy Google response parser accepts signed final text.")
