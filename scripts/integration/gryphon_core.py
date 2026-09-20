"""Isolated synthetic Core for the Gryphon browser/process qualification."""
import os
from pathlib import Path

import uvicorn

from mastermind.api import create_app
from mastermind.config import Config
from mastermind.context_indexing.template import DEFAULT_PATH, DEFAULT_TEMPLATE

if os.environ.get("MASTERMIND_GRYPHON_FIXTURE") != "isolated-synthetic-v1":
    raise SystemExit("This fixture must only run in an isolated test container")

config = Config(home=Path("/fixture-data"), public_url="http://localhost:18496",
                runtime_mode="offline", test_mode=True, secret_backend="development-files",
                secret_directory=Path("/credentials"), gryphon_socket="/run/gryphon/client.sock",
                gryphon_token_file=Path("/credentials/mastermind.token"))
for relative, text in {"root.md": "# root\n[[pool]]", "root/pool.md": "# pool\n#key", DEFAULT_PATH: DEFAULT_TEMPLATE}.items():
    target = config.vault / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
app = create_app(config)
uvicorn.run(app, host="0.0.0.0", port=18390, access_log=False)
