# Sharing

A Share grants access to one path-bound note projection. It uses a signed capability, optional password, expiry and explicit revocation, following Saturn's public sharing semantics. Owner management is authenticated; public capability possession never grants owner, Runtime, resource-reader or Crusher privileges.

Paths intentionally determine identity. Rename/move follows the managed path change. After deleting a note and creating another note at the same path, an existing Share can become readable again; this is an accepted product decision. Revoking the Share prevents that revival. This behavior must be considered before reusing paths for different content.

## Safe view and editing

The public view is a restricted Markdown projection. It does not resolve `@` references, native wikilinks, embeds, external URLs or internal/attachment resources. Sanitization applies on the server to both saved public text and rendered content; removing a few visible characters in the browser is not the authorization boundary. HTML, encoded links and alternate Markdown syntaxes cannot obtain resource grants.

An editable Share is still scoped to that one note. It uses the issued edit capability, CSRF/origin checks and the current ETag. A stale save receives a conflict after native buffers have been flushed; it never overwrites a later owner edit. Public writes do not count as owner Activity. Note/source bodies and passwords are omitted from audit output.

## Creating and copying links

The owner overlay accepts a note path, View/Edit access, optional local expiry
date/time and optional password. The explicit Create share gesture copies the
URL and closes the overlay. If the browser rejects clipboard access, the record
shows a selectable full URL and a fresh Copy link action. Copy works after
reload or another owner login through authenticated `GET /api/v1/shares/{id}/link`.
It does not change policy or invalidate existing links and sessions.

New tokens consist of `v2_` plus base64url-encoded 16-byte record ID and full
32-byte HMAC. The MAC uses the existing Volt/Kernel-resolved Share pepper and a
distinct `share-link-v2` domain. The database retains the canonical token HMAC
for backup/revocation compatibility; raw capabilities are not stored. Knowing a
record ID alone cannot produce a valid link. Existing 43-character random URLs
remain accepted. Copying an older record yields its deterministic signed alias;
both forms refer to the same policy, expiry, path and irreversible revocation.

No database migration is needed. Preserve the existing versioned Share pepper
with recovery material. Old application binaries do not recognize v2 URLs:
rolling back to them prevents newly issued/copied signed links from opening,
although legacy URLs remain compatible. An update/rollback plan must account
for this token-format change, not just database schema compatibility.

An empty password means Off. Every nonempty string is accepted, including `1`,
without minimum length or composition checks. A 4096-byte UTF-8 request-value
ceiling bounds resource use. Passwords remain Argon2 verifiers; unlock rate
limits remain enforced. Editing a policy with an empty password field keeps the
current password unless Remove password is selected. Policy changes invalidate
all of that Share's visitor sessions and projections.

## Direct editing and collision policy

Protected links first show a centered password gate with service reachability.
After unlocking, the title appears directly above the note. View permission
renders sanitized Markdown; Edit permission opens inline Markdown fields
immediately without an Edit toggle. Protected blocks are immutable placeholders.

The browser saves after 900ms without input, or on Ctrl/Cmd+S, with one write in
flight. Text typed while that write completes is retained and scheduled next.
Clean pages refresh every five seconds. A read that returns after typing starts
cannot replace the draft. Drafts stay in page memory, with an unsaved-changes
warning on close; there is no offline draft persistence or real-time CRDT merge.

The canonical `.md` file is authoritative; SQLite contains its derived index
and Share/service state. Every accepted public write follows this boundary:

1. Acquire the coordinator/process lock, pause the native writer and flush dirty
   Obsidian buffers through the Runtime/Bridge protocol.
2. Recheck capability, session, policy, projection and the strong SHA-256 ETag
   against the now-current file. A mismatch returns HTTP 409 with a fresh safe
   projection. No public bytes are committed on this path.
3. Validate editable values and reconstruct the original protected fragments.
   Recheck authorization, commit through the durable coordinator journal and
   atomically replace the canonical file, then reindex and resume the Runtime.

On 409, the page shows the current version above the retained draft and pauses
autosave. The visitor merges into the current editor and chooses Save merged
changes. That save uses the fresh ETag, so a second collision is checked again.
This applies to two visitors, an owner API write and native Obsidian edits.
The policy favors explicit review over silent last-write-wins, including changes
to different paragraphs. Revocation, expiry and permission changes stop writes.

`probe_public_editing.cjs` qualifies actual server saves, two browser sessions,
in-flight typing, polling races, explicit merge and protected-byte preservation.
`probe_native_shared.cjs` qualifies the same collision against a real edit in
the native Obsidian viewport using one disposable note. Both clean up their test
notes and revoke only their own Shares.

All shared pages and APIs are no-store/non-indexable. Share tokens do not appear in referrer headers, navigation collections, sitemaps or unredacted Nginx access paths. Noindex does not replace capability checks. Invalid, expired, wrong-password and revoked capabilities are qualified independently in [tests](../tests/test_shared.py) and the browser evidence recorded in [IMPLEMENTATION](IMPLEMENTATION.md).
