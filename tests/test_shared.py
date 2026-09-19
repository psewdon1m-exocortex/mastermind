import json
import time
from contextlib import contextmanager

import pytest

from mastermind import share_projection as projection
from mastermind.errors import DomainError
from mastermind.fs import sha_bytes
from mastermind.shared import Shared, SharedConflict


@pytest.fixture
def shared(recovery):
    backup, _, auth = recovery
    return Shared(backup.vault, auth, backup.secrets, backup.audit)


def opened(shared, source="Hello\n\n@private\n\nLast paragraph.\n", **policy):
    shared.vault.write("Folder/Shared.md", source, None, create=True)
    created = shared.create("Folder/Shared.md", **{"permission": "edit", **policy})
    token = created["url"].rsplit("/", 1)[1]
    session = shared.unlock(token, policy.get("password"), "192.0.2.7")
    return token, session, created


@pytest.mark.parametrize("text", [
    "", "No forbidden content\n", "Line\r\n\r\n@secret\r\n\r\nLast\r\n",
    "Ordinary\u2028text\n\n<!-- hidden\nDO NOT PUBLISH\n-->\n\nVisible\n",
    "---\nsecret: hidden\n---\n\n# Title\n\nBody\n",
    "---\rsecret: hidden\r---\r\rBody\r", "\ufeff---\nprivate: yes\n---\n\nBody",
    "![[Private]]\n\nMore\n", "[private](../never-open.md)\n\nMore\n",
    "[private][r]\n\n[r]: https://secret.test\n", "[private]\n\n[private]: ./secret.md\n",
    "```md\n@literal [[not resolved]] https://private.test\n```\n\nAfter\n",
    "    @code\n\nAfter\n", "- Visible\n- @secret\n\nAfter\n",
    "<script>fetch('https://secret.test')</script>\n\nAfter\n",
    "<div>\nSECRET BODY\n</div>\n\nAfter\n",
    "&lt;iframe src=&#x22;https://secret.test&#x22;&gt;\n\nAfter\n",
    "MMProtectedFragmentBoundary0End\n\n@target\n", "## @target\n\nBody\n",
    "@ x [[ ]] https://a.test www.test urn:test obsidian://open \n",
])
def test_projection_identity_is_lossless_even_for_existing_forbidden_literals(text):
    record = projection.partition(text)
    assert projection.join(record["values"], record["fragments"]) == text
    assert projection.reconstruct(record, record["values"], 1024**2) == text
    exposed = projection.public(record)
    assert "<a " not in exposed["html"] and "<img" not in exposed["html"]


@pytest.mark.parametrize("addition", [
    "@secret", "[[secret]]", "]]", "[link](secret.md)", "![x](file.png)", "[r]: ../file.md",
    "https://example.test", "www.example.test", "obsidian://open", "<img src=x>", "<svg onload=x>",
    "&#64;secret", "%40secret", "%2540secret", "＠secret", "［［secret］］", "[x]&#40;file.md)",
    "h\u200bttps://secret.test", "&lt;script&gt;", "!%5b%5bsecret%5d%5d", "[s]\n(./file)",
])
def test_new_references_are_rejected_after_decoding(addition):
    record = projection.partition("Visible\n\n@old\n\nLast\n")
    values = record["values"].copy()
    values[-1] += "\n" + addition
    with pytest.raises(DomainError) as failure:
        projection.reconstruct(record, values, 1024**2)
    assert failure.value.code == "REFERENCE_NOT_ALLOWED"


@pytest.mark.parametrize("prefix", ["```\n", "~~~\n", "    ", "> ", "- ", "---\n"])
def test_cannot_recontextualize_protected_content(prefix):
    record = projection.partition("Text\n\n@private\n\nEnd\n")
    values = record["values"].copy()
    values[0] = prefix
    with pytest.raises(DomainError, match="Protected content"):
        projection.reconstruct(record, values, 1024**2)


def test_cross_segment_reference_definition_and_no_disclosure():
    record = projection.partition("Text\n\n[secret]: ./other.md\n\nEnd\n")
    values = record["values"].copy()
    values[0] = "[secret]\n\n"
    with pytest.raises(DomainError):
        projection.reconstruct(record, values, 1024**2)
    public = json.dumps(projection.public(record))
    assert "other.md" not in public and "[secret]" not in public
    private = projection.partition("---\nprivate: CANARY1\n---\n\nVisible\n\n<!-- mastermind:crusher\nCANARY2\n-->\n")
    assert "CANARY" not in json.dumps(projection.public(private))


def test_public_edit_preserves_hidden_bytes_and_creates_no_owner_activity(shared):
    token, session, _ = opened(shared)
    view = shared.project(token, session["token"])
    values = [part["value"] for part in view["segments"] if part["kind"] == "text"]
    values[0] = "Changed public paragraph\n\n"
    saved = shared.save(token, session["token"], view["projection_id"], values, view["sha256"])
    assert saved["sha256"] != view["sha256"]
    assert shared.vault.read("Folder/Shared.md") == "Changed public paragraph\n\n@private\n\nLast paragraph.\n"
    assert shared.state.one("SELECT COUNT(*) AS n FROM activity")["n"] == 0
    assert shared.state.one("SELECT * FROM outbox WHERE path='Folder/Shared.md'")
    assert shared.audit.page()[-1]["action"] == "share.edit"


def test_token_password_session_scope_and_policy(shared):
    token, session, created = opened(shared, password="separate share password")
    assert token.startswith("v2_") and len(token) == 67
    stored = json.dumps(shared.state.rows("SELECT * FROM shares"))
    assert token not in stored and "separate share password" not in stored
    assert all("url" not in row and "token_hmac" not in row for row in shared.list())
    with pytest.raises(DomainError):
        shared.auth.session(session["token"])
    another = shared.create("Folder/Shared.md")["url"].rsplit("/", 1)[1]
    with pytest.raises(DomainError):
        shared.project(another, session["token"])
    shared.change(created["share_id"], {"permission": "view"})
    with pytest.raises(DomainError):
        shared.project(token, session["token"])
    renewed = shared.unlock(token, "separate share password", "192.0.2.7")
    view = shared.project(token, renewed["token"])
    with pytest.raises(DomainError) as denied:
        shared.save(token, renewed["token"], view["projection_id"], [], view["sha256"])
    assert denied.value.status == 403


@pytest.mark.parametrize("password", [None, "", "1", "short", "with\nline break", "😀"])
def test_optional_password_has_no_complexity_or_minimum_length(shared, password):
    token, session, _ = opened(shared, password=password)
    assert shared.project(token, session["token"])["permission"] == "edit"
    assert shared.describe(token)["password_required"] == bool(password)


def test_repeatable_signed_link_and_legacy_link_share_one_revocation_authority(shared):
    import secrets
    token, _, created = opened(shared)
    assert shared.copy_link(created["share_id"])["url"].endswith(token)
    assert token not in json.dumps(shared.state.rows("SELECT * FROM shares"))
    legacy = secrets.token_urlsafe(32)
    with shared.state.transaction() as db:
        db.execute("UPDATE shares SET token_hmac=? WHERE id=?", (shared.mac("share-token", legacy), created["share_id"]))
    copied = shared.copy_link(created["share_id"])["url"].rsplit("/", 1)[1]
    for value in (legacy, copied):
        assert shared.active(value)["id"] == created["share_id"]
    forged = copied[:-1] + ("A" if copied[-1] != "A" else "B")
    with pytest.raises(DomainError):
        shared.active(forged)
    shared.change(created["share_id"], {"revoke": True})
    for value in (legacy, copied):
        with pytest.raises(DomainError):
            shared.active(value)
    with pytest.raises(DomainError):
        shared.copy_link(created["share_id"])


def test_independent_editors_cannot_silently_overwrite_each_other(shared):
    token, first, _ = opened(shared)
    second = shared.unlock(token, None, "192.0.2.8")
    a, b = shared.project(token, first["token"]), shared.project(token, second["token"])
    av = [part["value"] for part in a["segments"] if part["kind"] == "text"]
    bv = [part["value"] for part in b["segments"] if part["kind"] == "text"]
    av[0] = "First editor saved\n\n"
    shared.save(token, first["token"], a["projection_id"], av, a["sha256"])
    bv[0] = "Second editor draft\n\n"
    with pytest.raises(SharedConflict) as collision:
        shared.save(token, second["token"], b["projection_id"], bv, b["sha256"])
    assert "First editor saved" in shared.vault.read("Folder/Shared.md")
    assert "Second editor draft" not in shared.vault.read("Folder/Shared.md")
    assert "First editor saved" in collision.value.projection["html"]
    assert "@private" not in json.dumps(collision.value.projection)
    assert "@private" in shared.vault.read("Folder/Shared.md")


def test_failed_unlock_limit_is_shared_across_capabilities_and_success_does_not_consume(shared):
    token, _, _ = opened(shared, password="correct password")
    second = shared.create("Folder/Shared.md", password="correct password")["url"].rsplit("/", 1)[1]
    for _ in range(7):
        assert shared.unlock(token, "correct password", "192.0.2.7")["token"]
    for index in range(5):
        with pytest.raises(DomainError) as failure:
            shared.unlock(token if index % 2 else second, "wrong", "192.0.2.7")
        assert failure.value.status == 401
    with pytest.raises(DomainError) as failure:
        shared.unlock(second, "correct password", "192.0.2.7")
    assert failure.value.status == 429
    assert "192.0.2.7" not in json.dumps(shared.state.rows("SELECT * FROM rate_limits"))


def test_live_path_revival_and_irreversible_revocation(shared):
    token, session, created = opened(shared)
    path = "Folder/Shared.md"
    shared.vault.delete(path, sha_bytes(shared.vault.read(path).encode()))
    with pytest.raises(DomainError) as missing:
        shared.project(token, session["token"])
    assert missing.value.status == 410 and shared.list()[0]["target_missing"]
    shared.vault.write(path, "A different note\n", None, create=True)
    assert "different" in shared.project(token, session["token"])["html"]
    shared.change(created["share_id"], {"revoke": True})
    for candidate in (token, "x"*43, "invalid"):
        with pytest.raises(DomainError) as hidden:
            shared.describe(candidate)
        assert hidden.value.status == 404 and hidden.value.message == "Share not found."
    with pytest.raises(DomainError) as final:
        shared.change(created["share_id"], {"expires_at": None})
    assert final.value.status == 409


def test_revoked_shares_are_removed_before_pagination_and_keep_their_tombstones(shared):
    token, session, created = opened(shared)
    kept = shared.create("Folder/Shared.md")
    shared.change(created["share_id"], {"revoke": True})
    assert [row["share_id"] for row in shared.list(limit=1)] == [kept["share_id"]]
    assert shared.list(limit=1, offset=1) == []
    row = shared.list()[0]
    assert row["size_bytes"] == len(shared.vault.read("Folder/Shared.md").encode("utf-8"))
    assert row["modified_at"] > 0 and not row["target_missing"]
    assert shared.state.one("SELECT revoked_at FROM shares WHERE id=?", (created["share_id"],))["revoked_at"]
    with pytest.raises(DomainError):
        shared.project(token, session["token"])


def test_policy_rechecked_after_quiesce(shared, monkeypatch):
    token, session, created = opened(shared)
    view = shared.project(token, session["token"])
    boundary = shared.vault.coordinator.boundary

    @contextmanager
    def expire(*args, **kwargs):
        with boundary(*args, **kwargs) as identifier:
            with shared.state.transaction() as db:
                db.execute("UPDATE shares SET expires_at=? WHERE id=?", (time.time()-1, created["share_id"]))
            yield identifier

    monkeypatch.setattr(shared.vault.coordinator, "boundary", expire)
    with pytest.raises(DomainError) as denied:
        shared.save(token, session["token"], view["projection_id"], [], view["sha256"])
    assert denied.value.status == 404
    assert shared.vault.read("Folder/Shared.md").startswith("Hello")


def test_stale_projection_returns_only_safe_current_content(shared):
    token, session, _ = opened(shared)
    view = shared.project(token, session["token"])
    shared.vault.write("Folder/Shared.md", "New paragraph\n\n@CANARY\n", view["sha256"])
    with pytest.raises(SharedConflict) as conflict:
        shared.save(token, session["token"], view["projection_id"], [], view["sha256"])
    assert "CANARY" not in json.dumps(conflict.value.projection)
    assert "New paragraph" in conflict.value.projection["html"]
    with pytest.raises(DomainError) as required:
        shared.save(token, session["token"], view["projection_id"], [], None)
    assert required.value.status == 428


def test_projection_is_bound_to_session_and_bounded(shared):
    token, session, _ = opened(shared)
    original = shared.project(token, session["token"])
    second = shared.unlock(token, None, "192.0.2.8")
    with pytest.raises(DomainError) as denied:
        shared.save(token, second["token"], original["projection_id"], [], original["sha256"])
    assert denied.value.status == 401
    for _ in range(25):
        shared.project(token, second["token"])
    assert shared.state.one("SELECT COUNT(*) AS n FROM projections")["n"] <= 10


@pytest.mark.parametrize("password", ["a"*4097, "😀"*1025, 123])
def test_password_policy(shared, password):
    with pytest.raises(DomainError) as failure:
        shared.password(password)
    assert failure.value.code == "INVALID_PASSWORD"
