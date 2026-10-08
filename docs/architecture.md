# Architecture

Mastermind is one independently released service with three Linux amd64 containers.
[Requirements](requirements.md) defines product scope; [Governance](governance.md)
maps the current central rules. The Vault tab inherits Obsidian UI/UX; the owned
Shell follows Part 01. This source topology is separate from deployment acceptance.

```text
Browser -> host Nginx :443 -> loopback Core :18390
                              |-- private Runtime :8091 / KasmVNC :8090
                              |     official Obsidian -> signed Bridge :8092 on loopback
                              |-- private Worker :8092 -> bounded source/provider requests
                              |-- Kernel -> Volt references for Shell secrets
                              |-- Chronos service reader
                              |-- Neptune host UDS -> Saturn -> SFTP
                              |-- Wyvern host UDS -> scoped model Adapter -> provider
                              |-- Gryphon host UDS -> paired Telegram adapter
                              `-- Updater host UDS -> the registered three-container group
```

Core owns the authoritative service SQLite database, durable journals, Activity and reference history, Share policy, Crusher jobs and settings. Markdown and opaque attachments/configuration under the canonical Vault are authoritative user data. Search, graph and embedding projections are disposable derived state. The Runtime never mounts the Core database. Worker never mounts the Vault or Core state and cannot commit a note.

## Storage and mutation boundary

The `vault-data` volume holds generation directories. Core sees `/data/vault/current`; Runtime sees `/vault/current`. Both mount the parent, so a verified generation switch becomes visible after the editor restarts. No writable live file is hardlinked into a snapshot.

Core's mutation coordinator serializes managed writes, native rename, public Share saves, Crusher commit, snapshot and restore. It requests Bridge quiescence, verifies saved native buffers, stops the Obsidian process and checks for surviving descendants before replacing canonical bytes. An unavailable Bridge cannot authorize a live writer bypass. A durable journal resolves interruptions between filesystem and SQLite changes. Unexpected external/plugin writes trigger validation and can latch NOT_READY.

Obsidian owns native `[[links]]` propagation through its FileManager. Bridge and Core coordinate `@references`, use the same Unicode fixtures and exclude code, comments, frontmatter and email. Canonical note basenames are globally unique after NFC and full case folding. Share identity intentionally remains path based; deleting and recreating a path can expose its replacement through an existing Share.

## Principals and recovery

Owner sessions, public Crusher sessions/status tickets, Share capabilities, Runtime/Bridge, Worker, Chronos reader, Neptune export/control and Updater own-head credentials are separate principals. Kernel discovery supplies service origins and the Shell's Volt references. Existing Obsidian plugin secrets remain opaque Vault data.

Archive and mirror are independent Neptune capabilities with separate credentials
and receipts. The central contract permits either or both; paired profiles share
one service-owned scheduling control. Only the encrypted archive includes mandatory
service state. Mirror is a protected Vault tree with a distinct read-only resource
reader. See [Backup](backup-restore.md) and [Compatibility](compatibility.md).

The default host dependency set is Updater, Neptune, Gryphon and Wyvern. Enabling a
particular integration is separate from ensuring its local agent. Core mounts only
its scoped client sockets and credentials. Gryphon owns bot tokens and paired
Telegram identities; Wyvern owns model Adapter transport/provider credentials.
Host installation and release operations belong to the Updater TUI.

## Weaver graph work engine

[Weaver](WEAVER.md) is the internal Core module for scoped knowledge lookup, note
similarity, reference traversal and policy-controlled placement. Its Bibliotekar
assistant runs locally in the existing Worker. Crusher owns source processing and
generation; Weaver owns placement decisions and executes the final write through
Core's canonical coordinator. Generic search does not inherit Crusher anchor rules.
Faiss accelerates exact scoped vector blocks; SQLite projections remain derived.
The rename adds neither a deployment unit nor a public listener.
