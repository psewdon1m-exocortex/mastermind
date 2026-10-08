# Backup and restore

The encrypted recovery ZIP and Neptune mirror serve different purposes. Recovery includes the whole Vault and mandatory service state. Mirror is a private Vault tree for synchronization and reading; it cannot restore Share policy, owner Activity or job history.

## Manual actions in Settings

The Backup card follows Volt's two pairs of manual actions:

| Download | Restore | Scope |
| --- | --- | --- |
| Create and download snapshot | Restore ZIP snapshot | Encrypted whole-service logical recovery: Vault plus mandatory Mastermind state |
| Download Vault ZIP | Restore Vault ZIP | Complete Obsidian Vault folder, without Shell state or archive encryption |

The first pair remains full service recovery, not a settings-only export. The second
pair is the functional-data equivalent of Volt's `personal.volt` export and import.
It works without recovery keys or an available Kernel, Neptune or Wyvern connection.

The download is named `vault.zip` and places the **contents of the actual Vault root** at the ZIP root. It includes
Markdown, attachments, empty directories, `.obsidian`, themes, snippets, plugin binaries
and plugin data, without inserting a manifest or changing file bytes. Unzip into a
directory and open that directory as a Vault in standard Obsidian; a notes subfolder
named `root/` remains a subfolder. Chronos/Saturn references are preserved, but their
remotely stored contents are not downloaded into the archive. This export is distinct
from the legacy portable API, which adds a Bridge reference-history snapshot.

Restore Vault ZIP opens a file-selection overlay and uploads into private staging.
Inspection checks the ZIP directory before allocating entries, paths, file types,
size/expansion bounds, CRCs, complete extraction and supported Markdown. It displays
note/file/folder counts, expanded size and root layout before explicit replacement.
ZIP64, stored and deflated files are supported. A single enclosing folder is removed
only when it clearly contains `.obsidian`; an ordinary `root/` folder is never stripped.
Empty Vaults also round-trip. Encrypted recovery ZIPs must use Restore ZIP snapshot.
The upload and confirmation bind the exact SHA-256; an altered staged archive fails.
Plain ZIP integrity checks do not establish publisher authenticity: import trusted
Vaults, since their Obsidian plugins are retained.

Restoration replaces the entire Vault, not a merge. Current Mastermind settings,
Access Key verifier, service connections, backup scheduling intent, Activity and job
history stay in place. Derived indexes are cleared and rebuilt. Active owner/visitor
sessions, Crusher codes and leases end; all existing Shared links are revoked to
prevent old URLs exposing different imported notes at matching paths. Incomplete
Crusher jobs fail with `SOURCE_UNAVAILABLE` and need resubmission. Obsidian settings
come from the ZIP. The pinned release's three managed Bridge artifacts are reinstalled
and enabled; other plugin files and Bridge user data are retained.

The native writer is stopped while copying/switching. Restore reuses the paired
Vault/SQLite journal, verifies a private copy with Runtime before commit and rolls
both back if verification fails. The old generation is retained until the operation
settles, then removed; download the current Vault first if a later manual return is
needed. Unlike full service recovery, this operation needs no encrypted safety ZIP.
Sign in again with the current Access Key to review completion. Downloads are streamed
and their server copies removed when the transfer ends; interrupted downloads require
a fresh export. Idle staging expires after 15 minutes, and Remove clears it sooner.

## Inventory

| Data | Recovery treatment |
| --- | --- |
| Markdown, attachments, empty folders, `.obsidian`, plugin/config/theme/snippet files | Opaque user data, byte-for-byte in the encrypted payload |
| Native plugin secrets and binaries | Preserved; never migrated to Volt or inspected as Shell credentials |
| Release-owned Bridge | Recorded and checked against the compatible signed release; user plugin data retained |
| Activity, reference history, Share hashes/policies/revocations, settings, Access Key verifier, job commit records | Mandatory typed service state |
| Sessions, one-time codes, status tickets, active leases | Invalidated at restore |
| FTS, graph, embeddings and caches | Rebuilt from authoritative data |
| `.env`, raw Shell/agent/provider keys, host configuration, logs and staging | Excluded; separate recovery escrow |
| Container images, local model and OS binaries | Reconstructed from verified immutable release artifacts |

The external ZIP contains `manifest.json` and `payload.age`. The manifest is signed using a dedicated Ed25519 backup identity, separate from release signing. The payload uses age/X25519. The consumer trusts the externally configured backup public key, never a key obtained only from the archive itself. An intact checksum is insufficient without signature and structural validation.

## Snapshot and restore transaction

A snapshot reserves disk space, flushes and stops the native writer under the mutation gate, copies a consistent Vault and SQLite snapshot, records inventory/hashes and resumes the writer. Compression/encryption of ordinary backups occurs from immutable staging. Network transfer streams bounded chunks; incomplete exports receive no completion receipt.

Restore accepts a streamed bounded ZIP into private staging, checks trust and actual bytes, decrypts and validates member paths, sizes, hashes and typed state. It rejects traversal, duplicate/casefold paths, symlinks, hardlinks, special entries and excessive expansion. Inspection precedes the explicit replacement confirmation. A new generation is opened by the pinned native Runtime and verified Bridge before the canonical pointer is committed. Sessions are revoked. Indexes and history are rebuilt; settled old generations and safety staging are removed after commit or verified rollback.

The recovery journal distinguishes pre-commit rejection from a committed generation whose later cleanup/audit/resume needs attention. A diagnostic failure after commit cannot turn a completed data replacement into a fictitious rollback. Pending recovery prevents new writes. Never delete the old generation or journal to suppress an error.

## Bounds and prerequisites

Defaults: 8 GiB compressed, 32 GiB expanded, 100,000 members, depth 64, 8 GiB per member, maximum ratio 1000:1; backup/recovery spool 96 GiB. Reservations also account for the retained old state and filesystem space available to UID 10001. The representative qualification fixture is approximately 350 MiB. Passing that fixture does not waive maximum-size bounds or promise sufficient disk on every host.

Plain Vault ZIP uses the same size and spool ceilings, a 64 MiB central-directory
ceiling and the configured note-size limit (8 MiB by default). The entry limit also
counts implied directories. Case/Unicode aliases, file-directory conflicts, links,
special files, unsupported compression and encrypted entries are rejected before
live replacement. Mastermind's unique Markdown-basename rule still applies on import.

Keep the compatible release, backup trust public key, age identity, required pepper versions and deployment bootstrap credentials outside the archive. Restoring Kernel/Volt or host agents is a separate operation. After a restore, verify note and attachment hashes, native open/Bridge, Activity/Share behavior and each declared Neptune pipeline with a fresh remote receipt. [IMPLEMENTATION](IMPLEMENTATION.md) records actual acceptance results and incomplete gates.

## Weaver state and compatibility

Schema 2 adds derived context metadata, branch profiles and bounded traces.
Recovery imports support schemas 1 and 2. Pool/template configuration and job
receipts are mandatory state; template files and Crusher outputs are canonical
Vault data. Derived context/semantic projections are rebuilt. Older Core must
not open schema 2; rollback requires the managed update preimage or a compatible
restore. The context-indexing tests include a real encrypted round trip of the
new configuration, template and `root/crusher` output.

## Remote capability profiles and schedule ownership

The current central enrollment contract permits archive, mirror or both. Archive
transfers full service recovery; mirror transfers the Vault tree and enrolls the
separate Saturn resource reader. An archive-only profile has no resource reader;
a mirror-only profile cannot execute archive operations. Require every declared
capability, not an undeclared second pipeline, when deciding readiness.

Settings authors the selected schedule intent. A paired profile applies one enabled
state and hourly interval to both schedules atomically while displaying separate
status and receipts. Saturn enforces identity/storage policy and observes progress;
it is not another schedule editor. Shared-agent release actions use the host TUI.
Preserve revision and pending reconciliation through restore; an offline agent
cannot be shown as having applied a merely saved policy. See [Conformance](conformance.md)
for remaining profile qualification.

## Update copies

Ordinary recovery/Vault ZIP limits above do not establish update transport capacity.
The central update contract has a default 128 MiB decoded ZIP ceiling at the
privileged boundary and requires the smallest supported end-to-end bound. Update
archives must use transient memory or verified tmpfs and the exact copy downloaded
to the operator. Later recovery verifies the original ZIP against the job's digest.
The inspected Core still uses filesystem staging; this is a documented gap in
[Conformance](conformance.md), not permission to retain update archives on disk.
See [Releases](releases.md#apply-and-automatic-recovery).
