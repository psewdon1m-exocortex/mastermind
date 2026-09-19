"""Non-secret own-client recovery intent. Restoring never writes shared gateway state."""
import json
import re

from .errors import DomainError

KEY = "wyvern.binding_intent"
SCHEMA = "exocortex.wyvern.binding-intent.v1"
ID = re.compile(r"[a-z][a-z0-9_-]{0,63}")


def validate(value):
    if not isinstance(value, dict) or set(value) != {"schema", "state", "instance_id", "client_id", "revision", "bindings"} \
            or value["schema"] != SCHEMA or value["state"] not in ("unconfigured", "observed", "pending_verification"):
        raise DomainError("WYVERN_INTENT_INVALID", "Invalid Wyvern recovery intent.", 422)
    bindings = value["bindings"]
    if not isinstance(bindings, dict) or len(bindings) > 64:
        raise DomainError("WYVERN_INTENT_INVALID", "Invalid Wyvern function bindings.", 422)
    for function, binding in bindings.items():
        if not ID.fullmatch(function) or not isinstance(binding, dict) or set(binding) != {"adapter_id", "profile"} \
                or not all(isinstance(v, str) and ID.fullmatch(v) for v in binding.values()):
            raise DomainError("WYVERN_INTENT_INVALID", "Invalid Wyvern function binding.", 422)
    if value["state"] == "unconfigured":
        if bindings or any(value[k] is not None for k in ("instance_id", "client_id", "revision")):
            raise DomainError("WYVERN_INTENT_INVALID", "Invalid unconfigured Wyvern intent.", 422)
    elif not all(isinstance(value[k], str) and ID.fullmatch(value[k]) for k in ("instance_id", "client_id")) \
            or type(value["revision"]) is not int or value["revision"] < 1:
        raise DomainError("WYVERN_INTENT_INVALID", "Invalid Wyvern intent provenance.", 422)
    return value


def read(state):
    row = state.one("SELECT value FROM metadata WHERE key=?", (KEY,)) if state else None
    return validate(json.loads(row["value"])) if row else None


def save(state, value):
    value = validate(value)
    with state.transaction() as db:
        db.execute("INSERT INTO metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (KEY, json.dumps(value, sort_keys=True)))


def from_status(status):
    return validate({"schema": SCHEMA, "state": "observed", "instance_id": status.get("instance_id"),
                     "client_id": status.get("client_id"), "revision": status.get("binding_revision"), "bindings": status.get("bindings")})


def matches(intent, status):
    return all(intent[name] == status.get(name) for name in ("instance_id", "client_id", "bindings"))
