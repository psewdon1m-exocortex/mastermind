# Operations

## Shared, search and notifications

The owner destination is **Shared** at `/shared`; `/shares` remains a legacy
bookmark alias. Saved navigation order identifiers remain compatible. Each row
shows the note name, actual note modification time and permission; expanding it
shows password status, creation/expiry, size, status and policy/revoke actions.
Search and sorting apply to the current bounded page. Create share copies the
link and closes its overlay; Copy link remains available after reload or login.
Clipboard denial leaves the full URL selectable in the record. Passwords are
optional and have no minimum length or complexity rule. Revocation removes the row before server-side
pagination and invalidates visitor sessions while retaining the revocation
record and the underlying note.

Crusher and Shared use the canonical 40px search field with an 18px magnifier,
12px spacing and a permanently reserved 32px clear control. Notifications stack
at the upper right, at most five at a time, with green success/information and
red error outlines. They can be dismissed; ordinary lifetime is 4.5 seconds or
8 seconds respectively, paused while hovered or focused. Sidebar ordinals
remain visible without dot handles; drag the row or focus its link and use
Alt+Arrow Up/Down. Automatic sidebar reveal uses the invisible left edge, with
no arrow. Dashboard card handles remain.

Public Shared pages use a centered password gate when needed, then the note
title and content. Edit access exposes Markdown directly, with 900ms debounced
autosave and five-second refresh of clean pages. A stale version cannot replace
another writer's changes: the current version and retained draft are shown for
explicit merge. See [Sharing](sharing.md) for the native flush, journal and
version checks, link compatibility and recovery requirements.

For the processing stages, privacy bounds and verified local provider mode,
see [Crusher: processing contract and local readiness](crusher.md).

## Dashboard and operator guide

All Shell pages, dialogs and public Crusher/Shared pages suppress visual
scrollbars while retaining wheel, touch, keyboard and programmatic scrolling.
Documentation keeps its two independent scroll regions. This Shell rule does
not rewrite native Obsidian themes or editor configuration.

Dashboard contains CPU, RAM, Disk and Uptime followed by Connectedness (2x),
Total items (2x), Activity Heatmap (4x) and Crusher access (1x). Saved card and
navigation orders persist; obsolete Analytics/Service status entries are
filtered when preferences are read and newly available cards are appended.
The old `/analytics` browser destination redirects to Dashboard. The existing
authenticated analytics API remains the data source.

Total items counts regular non-hidden Vault files: Markdown notes plus images,
PDFs, canvases, audio, video and other attachments. It excludes folders, hidden
state, `.obsidian` and trash, without reading attachment or plugin contents.
Connectedness remains the internal note-graph percentage. Create & copy in the
Dashboard's Crusher access card issues the same one-use, 30-minute invitation.
The code and expiry replace the action in the card. Subsequent clicks copy that
code; clipboard denial retains the complete selectable value and allows retry.

The Vault toolbar offers Reconnect and Fullscreen. Recovery snapshots remain
in Settings → Backup; the owner portable-export API remains available.

Documentation follows [Part 01](policy/PART_01_INTERFACE_AND_INTERACTION_UNIFICATION.md):
grouped navigation and one continuous operator guide have separate bounded
scroll regions on desktop and mobile. Search includes titles, summaries,
keywords and body text; a changed query resets article scrolling. The active
topic follows the article's reading position. Clear search and Escape restore
the current collection and keep input focus. Search filters do not alter data.

## Host operations

For releases, `mastermind update check` discovers an approved candidate, `mastermind update apply <version>` starts a whole-group update, and `mastermind update status` observes its durable progress. `mastermind update previous` lists the verified previous version; `mastermind update rollback --job <id> --yes` returns to it using a fresh backup and preserves compatible current data. These commands use the running Core's private admin socket.

Run host commands from `/opt/exocortex/mastermind`. `mastermind-install status` describes containers; `mastermind-install doctor` checks canonical state and authenticated dependencies separately. The Core CLI talks to a private same-container Unix socket and does not publish administration over TCP.

```sh
sudo mastermind-install status
sudo mastermind-install doctor
docker exec mastermind-core-1 mastermind vault validate
docker exec mastermind-core-1 mastermind reindex
docker exec mastermind-core-1 mastermind graph rebuild
docker exec mastermind-core-1 mastermind replication status
docker exec mastermind-core-1 mastermind replication reconcile
```

## Startup and shutdown

Use `docker compose -f compose.production.yaml up -d --no-build` with the installed `.env`. For planned maintenance, finish pending owner operations and stop the owned group with `docker compose -f compose.production.yaml stop core runtime worker`. Do not use `down --volumes`. Runtime restart uses `docker compose -f compose.production.yaml restart runtime`; Core detects the new supervisor and repeats recovery/Bridge startup. Check readiness and the native editor before returning to work. A process kill is a fault test, not the normal way to save an active editor.

## Readiness and failures

`READY` requires canonical storage and authenticated dependency checks. `live`, `canonical_ready`, dependency status and external edge verification are independent. Missing observations are UNKNOWN, not zero. `NATIVE_OWNER_SETUP_REQUIRED` requires the first native trust step described in [deployment](deployment.md). `BRIDGE_UNAVAILABLE` after prior successful setup needs Runtime/log inspection. Do not override quiescence or manually remove a mutation journal.

`NOT_READY`, duplicate basenames, missing opaque data, `RECOVERY_REQUIRED` or `POST_RESTORE_RECOVERY_REQUIRED` stop writes. Preserve the entire service volumes and recovery directories before investigating. Correct an independently understood configuration/storage problem and restart the group to run journal recovery, then repeat `vault validate` and doctor. An unresolved generation/rollback marker requires recovery from a verified archive, not an ad hoc database edit.

If Kernel or Volt is unavailable, restore its own bootstrap/trust first. Mastermind recovery keys cannot be recovered solely from an archive encrypted by those keys. If Neptune is partial or unavailable, Settings distinguishes the state; retrieve a fresh setup code and use Repair. Archive and mirror success times/generations are separate. Saturn owns schedules, quotas, remote commands and revocation.

## Backup, restore and updates

Settings → Backup creates a full encrypted snapshot, supports streaming download and stages ZIP inspection before an explicitly confirmed restore. The equivalent CLI is:

```sh
docker exec mastermind-core-1 mastermind backup create
docker exec mastermind-core-1 mastermind operation OPERATION_ID
```

The resulting staged operation is retained for at most 24 hours; inspect its ID, size and SHA-256 before download. CLI `backup create --output /tmp/recovery.zip` requires an exclusive writable destination in that container. CLI `restore inspect /tmp/recovery.zip` and `restore apply /tmp/recovery.zip --yes` require a bounded regular source file, not a symlink/FIFO. Keep recovery keys outside the archive. See [backup-restore](backup-restore.md).

Settings → Updates checks the approved repository through the own host Updater. A compatible exact version can be applied after confirmation. Core prepares a recovery snapshot and retains the write barrier; Updater applies all three components and accepts only functional health. An interrupted response is reconciled through durable job identity. Failed migration/health triggers restoration of prior components and pre-update data. A failed rollback remains blocked and is never displayed as success. See [releases](releases.md) for release and rollback qualification.

## Diagnostics and retention

The current local Crusher stand is connected to real Google Gemini 3.8 Flash.
Submissions consume the provider account's quota. Use the tested image and local
live Compose override documented in [Crusher](crusher.md#operating-the-local-live-profile)
when restarting it; adding the controlled-provider override silently changes
the behavior back to a fixture. Provider credentials belong to Volt/Kernel.
The current source's Wyvern migration has a separate deployment contract and
must not be substituted for this image without its own qualification.

Settings contains a bounded log tail and a redacted archive download. Audit records omit raw credentials and note bodies. Use the configured Docker JSON log rotation and inspect free space on the actual Vault filesystem. Failed sources, completed operation spools and old restored generations have bounded retention; active uploads/download leases are protected. Do not clear the backup/recovery spool while an operation or host update is pending.

Logs and reports are not permission to expose internal URLs, `.env`, cookie values, provider keys, full Vault notes or original plugin configuration in a support message. Report the exact service version, operation/job ID, sanitized error code, stage and relevant bounded test evidence.

If a Runtime pause or native preparation response is lost before a mutation starts, Core cancels that exact identity and retries the cancellation after connectivity returns. Runtime rejects a delayed request carrying an already-cancelled identity. A lost safe resume response uses the same reconciliation. This does not release a retained update/recovery barrier. The cancellation ledger is bounded to 1,024 failed identities per Runtime boot; if repeated infrastructure failures exhaust it, new managed pauses fail with `RUNTIME_RESTART_REQUIRED`. Resolve the transport/storage fault, confirm that no update or recovery is pending, then restart only Runtime through the installed Compose group. Never clear a pending recovery to remove this message.
