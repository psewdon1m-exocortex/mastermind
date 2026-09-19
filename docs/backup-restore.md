# Backup and restore

The encrypted recovery ZIP and Neptune mirror serve different purposes. Recovery includes the whole Vault and mandatory service state. Mirror is a private Vault tree for synchronization and reading; it cannot restore Share policy, owner Activity or job history.

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

Restore accepts a streamed bounded ZIP into private staging, checks trust and actual bytes, decrypts and validates member paths, sizes, hashes and typed state. It rejects traversal, duplicate/casefold paths, symlinks, hardlinks, special entries and excessive expansion. Inspection precedes the explicit replacement confirmation. A new generation is opened by the pinned native Runtime and verified Bridge before the canonical pointer is committed. Sessions are revoked. Indexes and history are rebuilt, and successful old generations remain available for up to 24 hours under quota.

The recovery journal distinguishes pre-commit rejection from a committed generation whose later cleanup/audit/resume needs attention. A diagnostic failure after commit cannot turn a completed data replacement into a fictitious rollback. Pending recovery prevents new writes. Never delete the old generation or journal to suppress an error.

## Bounds and prerequisites

Defaults: 8 GiB compressed, 32 GiB expanded, 100,000 members, depth 64, 8 GiB per member, maximum ratio 1000:1; backup/recovery spool 96 GiB. Reservations also account for the retained old state and filesystem space available to UID 10001. The representative qualification fixture is approximately 350 MiB. Passing that fixture does not waive maximum-size bounds or promise sufficient disk on every host.

Keep the compatible release, backup trust public key, age identity, required pepper versions and deployment bootstrap credentials outside the archive. Restoring Kernel/Volt or host agents is a separate operation. After a restore, verify note and attachment hashes, native open/Bridge, Activity/Share behavior and both fresh Neptune pipelines. [IMPLEMENTATION](IMPLEMENTATION.md) records actual acceptance results and incomplete gates.

## Context-indexing state

Schema 2 adds derived context metadata, branch profiles and bounded traces.
Recovery imports support schemas 1 and 2. Pool/template configuration and job
receipts are mandatory state; template files and Crusher outputs are canonical
Vault data. Derived context/semantic projections are rebuilt. Older Core must
not open schema 2; rollback requires the managed update preimage or a compatible
restore. The context-indexing tests include a real encrypted round trip of the
new configuration, template and `root/crusher` output.
