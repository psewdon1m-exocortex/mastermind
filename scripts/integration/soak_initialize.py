"""Populate only the dedicated qualification volumes, without touching the main stack."""
import os
from pathlib import Path

for name in ("/data", "/vault", "/profile"):
    Path(name).mkdir(exist_ok=True)
    os.chown(name, 10001, 10001)
    os.chmod(name, 0o700)
root = Path("/vault/current")
if not root.exists():
    root.mkdir()
    (root / "root.md").write_text("# Root\n#main\n\n[[Knowledge]]\n", "utf-8")
    (root / "Knowledge.md").write_text("# Knowledge\n#key\n\n@root\n", "utf-8")
    (root / "Runtime soak.md").write_text("# Runtime soak\n\n@root [[Knowledge]]\n\n", "utf-8")
    for number in range(2000):
        folder = root / ("Branch " + str(number // 100))
        folder.mkdir(exist_ok=True)
        (folder / f"Topic {number:04}.md").write_text(f"# Topic {number:04}\n\n@Knowledge [[root]]\n\n" +
            "A representative local knowledge note with preserved Markdown. " * 8 + "\n", "utf-8")
    attachment = root / "Attachments"
    attachment.mkdir()
    chunk = os.urandom(1024**2)
    with (attachment / "representative.bin").open("xb") as output:
        for _ in range(350):
            output.write(chunk)
    for parent, directories, files in os.walk(root):
        for path in [Path(parent), *(Path(parent) / name for name in directories + files)]:
            os.chown(path, 10001, 10001)
            os.chmod(path, 0o700 if path.is_dir() else 0o600)
print("Runtime soak fixture: 2,003 notes and a 350 MiB attachment")
