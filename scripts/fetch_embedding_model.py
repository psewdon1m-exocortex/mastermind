"""Build-time only fetch of release-pinned offline embedding artifacts."""
import hashlib
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
MODEL = "intfloat/multilingual-e5-small"
FILES = {
    "onnx/model.onnx": (470268510, "ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665"),
    "onnx/tokenizer.json": (17082730, "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39"),
}


def main():
    destination = ROOT / ".local" / "models" / "multilingual-e5-small"
    destination.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        for name, (size, expected) in FILES.items():
            target = destination / Path(name).name
            if target.exists():
                with target.open("rb") as stream:
                    if target.stat().st_size == size and hashlib.file_digest(stream, "sha256").hexdigest() == expected:
                        continue
            temporary, digest, count = target.with_suffix(".download"), hashlib.sha256(), 0
            with client.stream("GET", f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}") as response:
                response.raise_for_status()
                with temporary.open("wb") as output:
                    for block in response.iter_bytes(1024**2):
                        count += len(block)
                        if count > size:
                            raise ValueError("Model artifact exceeded its pinned size")
                        digest.update(block)
                        output.write(block)
            if count != size or digest.hexdigest() != expected:
                raise ValueError("Model artifact did not match its release digest")
            temporary.replace(target)
            print("Verified " + Path(name).name, flush=True)
    lock = {"schema": "mastermind.embedding.v1", "model": MODEL, "revision": REVISION,
            "license": "MIT", "preprocessing": "query: / passage:; attention-mask mean pool; L2 normalization",
            "max_tokens": 512, "dimensions": 384, "runtime": "onnxruntime-cpu",
            "files": {Path(name).name: {"size": size, "sha256": digest} for name, (size, digest) in FILES.items()}}
    (ROOT / "embedding-model.lock.json").write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("Offline model inventory ready", flush=True)


if __name__ == "__main__":
    main()
