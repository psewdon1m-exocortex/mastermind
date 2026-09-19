"""Synthetic Core API using real local E5 in process; no provider or service credentials."""
import json
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, "/suite/scripts")
from qualify_context_indexing import OfflineWorker

from mastermind.api import create_app
from mastermind.config import Config


def main():
    assert json.loads(Path("/qualification/fixture.json").read_text())["fixture"] == "mastermind-related-notes/v1"
    worker = OfflineWorker(Path("/opt/mastermind/model"), Path("/app/embedding-model.lock.json"),
                           "/opt/mastermind/curator", "/app/curator-model.lock.json")
    config = Config(home=Path("/qualification/core"), secret_directory=Path("/qualification/secrets"),
                    public_url="http://localhost:18495", runtime_mode="offline", test_mode=True,
                    worker_url="http://127.0.0.1:1")
    app = create_app(config)
    service = app.state.service
    service.semantic.worker = worker
    requests = []

    @app.middleware("http")
    async def count_related(request, next_handler):
        if request.url.path == "/internal/bridge/related-notes":
            requests.append(1)
        return await next_handler(request)

    @app.get("/fixture/status")
    def status():
        return {"ready": service.ready, "search": service.semantic.status(), "requests": len(requests)}

    uvicorn.run(app, host="0.0.0.0", port=18495, access_log=False)


if __name__ == "__main__":
    main()
