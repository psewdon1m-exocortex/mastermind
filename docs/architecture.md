# Architecture

Mastermind is one independently released service with three Linux amd64 containers. The normative product contract is [requirements](../mastermind_service_requirements_final.md); the effective central rules are pinned in [policy-lock.json](policy-lock.json). The Vault tab deliberately inherits Obsidian UI/UX. The surrounding Shell follows Part 01.

```text
Browser -> host Nginx :443 -> loopback Core :18390
                              |-- private Runtime :8091 / KasmVNC :8090
                              |     official Obsidian -> signed Bridge :8092 on loopback
                              |-- private Worker :8092 -> bounded source/provider requests
                              |-- Kernel -> Volt references for Shell secrets
                              |-- Chronos service reader
                              |-- Neptune host UDS -> Saturn -> SFTP
                              `-- Updater host UDS -> the registered three-container group
```

Core owns the authoritative service SQLite database, durable journals, Activity and reference history, Share policy, Crusher jobs and settings. Markdown and opaque attachments/configuration under the canonical Vault are authoritative user data. Search, graph and embedding projections are disposable derived state. The Runtime never mounts the Core database. Worker never mounts the Vault or Core state and cannot commit a note.

## Storage and mutation boundary

The `vault-data` volume holds generation directories. Core sees `/data/vault/current`; Runtime sees `/vault/current`. Both mount the parent, so a verified generation switch becomes visible after the editor restarts. No writable live file is hardlinked into a snapshot.

Core's mutation coordinator serializes managed writes, native rename, public Share saves, Crusher commit, snapshot and restore. It requests Bridge quiescence, verifies saved native buffers, stops the Obsidian process and checks for surviving descendants before replacing canonical bytes. An unavailable Bridge cannot authorize a live writer bypass. A durable journal resolves interruptions between filesystem and SQLite changes. Unexpected external/plugin writes trigger validation and can latch NOT_READY.

Obsidian owns native `[[links]]` propagation through its FileManager. Bridge and Core coordinate `@references`, use the same Unicode fixtures and exclude code, comments, frontmatter and email. Canonical note basenames are globally unique after NFC and full case folding. Share identity intentionally remains path based; deleting and recreating a path can expose its replacement through an existing Share.

## Principals and recovery

Owner sessions, public Crusher sessions/status tickets, Share capabilities, Runtime/Bridge, Worker, Chronos reader, Neptune export/control and Updater own-head credentials are separate principals. Kernel discovery supplies service origins and the Shell's Volt references. Existing Obsidian plugin secrets remain opaque Vault data.

Archive and mirror are independent Neptune pipelines. Only the encrypted archive includes mandatory service state. Mirror is a protected Vault tree and an interactive reader uses a separate read-only scope. [Security](security.md), [backup](backup-restore.md) and [compatibility](compatibility.md) describe these boundaries in detail.
