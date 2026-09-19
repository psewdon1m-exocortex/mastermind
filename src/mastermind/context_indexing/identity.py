"""Settings follow proven canonical moves; observed deletions require explicit rebinding."""


def canonical_change(state, metadata, changes):
    configuration = state.setting("context_indexing")
    if configuration is None:
        return []
    invalid = state.setting("context_indexing_invalid_paths", {})
    moved = dict(metadata.get("moves", []))
    deleted = {item["path"] for item in changes if item["after"] is None}
    fields = []
    for field in ("fallback_note", "template_path"):
        path = configuration[field]
        if path in moved and field not in invalid:
            configuration[field] = moved[path]
            fields.append(field)
        elif path in deleted:
            invalid[field] = path
    root = state.setting("crusher_root", "root.md")
    if root in moved:
        state.set_setting("crusher_root", moved[root])
        fields.append("graph_root")
    if fields:
        configuration["revision"] += 1
        state.set_setting("context_indexing", configuration)
    state.set_setting("context_indexing_invalid_paths", invalid)
    return fields


def observed_deletions(state, deleted):
    configuration = state.setting("context_indexing")
    if configuration is None:
        return
    invalid = state.setting("context_indexing_invalid_paths", {})
    for field in ("fallback_note", "template_path"):
        if configuration[field] in deleted:
            invalid[field] = configuration[field]
    if invalid:
        state.set_setting("context_indexing_invalid_paths", invalid)
