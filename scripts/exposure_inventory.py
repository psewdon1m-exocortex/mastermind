"""Generate a reviewable route inventory; CI compares it with actual registrations."""
import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METHODS = {"get", "post", "put", "patch", "delete", "websocket"}


def discovered(root=ROOT):
    rows = []
    for path in sorted((root / "src/mastermind").glob("*.py")):
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and \
                            isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == "app" and decorator.func.attr in METHODS:
                        route = ast.literal_eval(decorator.args[0])
                        rows.append((path.name, decorator.func.attr.upper(), route))
            if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and node.target.id == "route" and \
                    any(isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "add_api_route" for call in ast.walk(node)):
                rows.extend((path.name, "GET", route) for route in ast.literal_eval(node.iter))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and \
                    node.func.value.id == "app" and node.func.attr == "mount":
                rows.append((path.name, "GET", ast.literal_eval(node.args[0]) + "/{path:path}"))
    return sorted(rows)


def classify(module, method, path):
    component, exposure = "core", "canonical_https"
    if module == "admin.py":
        component, exposure, principal = "core-admin", "owner_uid_unix_socket", "host_operator"
    elif module == "runtime_supervisor.py":
        component, exposure = "runtime", "private_network"
        principal = "local_health" if path == "/healthz" else "runtime_control"
    elif module == "worker.py":
        component, exposure, principal = "worker", "private_network", "worker_control"
    elif path.startswith("/internal/bridge/"):
        exposure, principal = "private_network", "bridge"
    elif path.startswith("/api/internal/neptune/"):
        exposure, principal = "loopback_and_export_identity", "neptune_export"
    elif path.startswith("/api/internal/updater/"):
        exposure, principal = "loopback_and_updater_identity", "updater_control"
    elif path == "/readyz":
        exposure, principal = "private_network", "local_health"
    elif path.startswith("/s/"):
        principal = "share_projection" if path.endswith("/api/note") else "share_entry"
    elif path == "/api/v1/crusher/sessions":
        principal = "one_use_crusher_code"
    elif path.startswith("/api/v1/crusher/") and path != "/api/v1/crusher/access":
        principal = "owner_or_crusher_session"
    elif path in {"/healthz", "/robots.txt", "/api/appearance", "/api/auth/login"} or path.startswith("/assets/") or path.count("/") == 1:
        principal = "public_bootstrap"
    else:
        principal = "owner"
    return {"component": component, "method": method, "path": path, "source": "src/mastermind/" + module,
            "exposure": exposure, "principal": principal, "indexable": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Generate a draft that must be reviewed before commit")
    args = parser.parse_args()
    path = ROOT / "docs/exposure-inventory.json"
    routes = [classify(*row) for row in discovered()]
    result = {"schema": "mastermind.exposure.v1", "mode": "non-indexable", "routes": routes}
    if args.write:
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
        print("Generated " + str(len(routes)) + " route classifications for review")
    elif json.loads(path.read_text("utf-8")) != result:
        raise SystemExit("Exposure inventory differs from registered source routes; review every changed boundary")
    else:
        print("PASS " + str(len(routes)) + " classified method/path/principal/exposure entries")


if __name__ == "__main__":
    main()
