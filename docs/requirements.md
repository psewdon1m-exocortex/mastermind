# Mastermind product contract

This is the active product overview, consolidated on **2026-10-06** from the
original requirements and subsequent owner decisions. Detailed behavior belongs
to the linked topic guides. [Central authority](governance.md) takes precedence;
[Conformance](conformance.md) separates implementation gaps from requirements.

## Knowledge and ownership

Mastermind keeps knowledge as ordinary Markdown and assets in an Obsidian Vault.
Core owns managed mutation, service state and recovery coordination. The pinned
native Runtime owns the editor; Worker performs bounded extraction and model work
without a Vault mount or commit authority. The owned Shell provides Dashboard,
Vault access, Shared, Crusher, Settings and Documentation.

The Vault remains the authoritative content store. Search, graph and embedding
indexes are disposable projections. Canonical Markdown basenames are unique after
NFC and full case folding. Filesystem nesting is not graph placement. Existing
`.obsidian` settings, plugin data and secrets remain opaque user data, including
during backup; they are not migrated into Shell credentials.

## Product capabilities

| Capability | Required boundary and detailed owner |
| --- | --- |
| Native editing and references | Preserve Obsidian editing and theme behavior. Bridge integrates custom note, Chronos and Saturn references with native views; [Bridge](mastermind-bridge.md). |
| Retrieval and graph work | Weaver performs Lookup, Similar, Walk and authorized placement, returning evidence to consumers. Answer generation is outside its responsibility; [Weaver](WEAVER.md). |
| Adaptive suggestions | Use the active, possibly unsaved editor context; return bounded relevant peers without saving that buffer or inventing links; [retrieval contracts](context-indexing.md). |
| Source intake | Crusher accepts bounded sources, owns understanding/generation through a selected Wyvern Adapter, validates the result and uses Weaver placement. Visitors see only their intake and progress; [Crusher](crusher.md). |
| Sharing | Grant access to one sanitized, path-bound note with optional password, expiry and revocation. Granted edits use conflict detection and explicit merge; [Sharing](sharing.md). |
| Owner activity | Count owner CREATE, EDIT, RENAME and MOVE events. Reading, indexing and public edits do not inflate owner activity; [Operations](operations.md). |
| Recovery and portability | Distinguish encrypted full-service recovery, plain complete Vault ZIP, and remote archive/mirror capabilities; [Backup](backup-restore.md). |
| External services | Resolve authorized connections through Kernel, keep Shell secrets in Volt, and use scoped host-agent clients; [Compatibility](compatibility.md). |
| Delivery | Release Core, Runtime and Worker as one verified group; publish standalone Bridge packages through their separate channel; [Releases](releases.md). |

## Invariants

Managed writes and restores use the canonical coordinator and durable journal;
an unavailable writer/quiescence boundary cannot authorize a bypass. Native
Obsidian handles wikilink rename propagation. Bridge/Core coordinate custom
references and preserve code/frontmatter/comment exclusions.

Owner, Share, public Crusher, Bridge, Worker and integration credentials are distinct
principals. An Access Key is the exact supplied opaque value without trimming,
normalization or a password-strength policy. Host Nginx owns public TLS and routing;
private Runtime/Worker/agent interfaces are not published. Mastermind content is
non-indexable. See [Security](security.md) and [API](api.md).

Full recovery includes Vault and mandatory service state. Plain Vault import replaces
the Vault while preserving Shell configuration and revoking existing Shares. An
archive or successful index rebuild alone is not a verified restore. Applications
own their remote schedules; Saturn observes and enforces storage authorization.
Shared-agent installation and updates belong to the host Updater lifecycle.

Limits must be enforced, errors must preserve recoverable state, and stale evidence
must not authorize mutation. A local fixture PASS, a historical deployed image and
an exact released candidate are different evidence. [Verification status](IMPLEMENTATION.md)
records those distinctions and [Releases](releases.md) defines publication gates.

## Earlier specifications

The original, adapted and September final requirements, question log, retrieval
design and general AI concept are preserved in [history](history/README.md).
Their obsolete schedules, bespoke graph views, Curator naming, provider setup and
update retention instructions are superseded by these active guides and central
rules. The wider AI-agent concept does not assert an implemented Mastermind agent
runtime or answer-generation service.
