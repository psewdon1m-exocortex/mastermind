"""Install only release-owned Bridge files; opaque user plugins remain untouched."""
import json

from .errors import DomainError
from .fs import atomic_json, atomic_write_under, resolve, sha_file


def install_bridge_files(vault, artifacts):
    expected = json.loads((artifacts / "integrity.json").read_text("utf-8"))
    if set(expected) != {"main.js", "manifest.json", "styles.css"}:
        raise DomainError("BRIDGE_INTEGRITY", "Bridge artifact inventory is invalid.", 503)
    for name, digest in expected.items():
        source = artifacts / name
        if sha_file(source) != digest:
            raise DomainError("BRIDGE_INTEGRITY", "Bridge artifact failed integrity verification.", 503)
        relative = ".obsidian/plugins/mastermind-bridge/" + name
        destination = resolve(vault, relative, internal=True)
        if sha_file(destination) != digest:
            atomic_write_under(vault, relative, source.read_bytes(), internal=True)
    plugins = resolve(vault, ".obsidian/community-plugins.json", internal=True)
    enabled = json.loads(plugins.read_text("utf-8")) if plugins.exists() else []
    if not isinstance(enabled, list) or not all(isinstance(p, str) for p in enabled):
        raise DomainError("INVALID_CONFIG", "The native plugin list is invalid.", 503)
    if "mastermind-bridge" not in enabled:
        atomic_write_under(vault, ".obsidian/community-plugins.json",
                           json.dumps([*enabled, "mastermind-bridge"]).encode(), internal=True)
    app_config = resolve(vault, ".obsidian/app.json", internal=True)
    if not app_config.exists():
        atomic_json(app_config, {"alwaysUpdateLinks": True})
