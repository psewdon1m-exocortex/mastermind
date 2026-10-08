# Mastermind documentation

Start with the [product contract](requirements.md) and [architecture](architecture.md).
These guides describe Mastermind's current source and required operating contract.
They do not establish that a particular deployment or release has passed acceptance.

The workspace `.docs` is the central authority. [Governance](governance.md) maps its
Parts to these guides and explains the separate, immutable release-evidence pin.
[Conformance](conformance.md) records known differences between the required contract
and inspected implementation. There is no second copy of central policy in this repository.

## Product and interfaces

| Guide | Use it for |
| --- | --- |
| [Requirements](requirements.md) | Product scope, ownership and stable invariants |
| [Architecture](architecture.md) | Core, Runtime, Worker, canonical storage and trust boundaries |
| [Bridge](mastermind-bridge.md) | Native Obsidian references, graph integration, Related notes and portable behavior |
| [Weaver](WEAVER.md) | Knowledge retrieval, graph traversal, evidence and placement concepts |
| [Retrieval contracts](context-indexing.md) | Detailed Weaver limits, configuration, evidence and compatibility names |
| [Crusher](crusher.md) | Intake, processing, Wyvern generation, placement and recovery |
| [Sharing](sharing.md) | Capability scope, editing, collision handling and revocation |
| [Public Shared presentation](public-shared.md) | Current public note/gate UI and retained legacy presentation |
| [API](api.md) | HTTP and internal contracts; authoritative route inventory links |

## Running and releasing Mastermind

| Guide | Use it for |
| --- | --- |
| [Deployment](deployment.md) | Host dependencies, installation, first native consent and ingress |
| [Operations](operations.md) | Owner workflows, host commands, readiness and diagnostics |
| [Backup and restore](backup-restore.md) | Full service recovery, plain Vault ZIP and remote pipeline scope |
| [Compatibility and integrations](compatibility.md) | Producer responsibilities, dependency qualification and discovery |
| [Gryphon](gryphon.md) | Paired Telegram adapter and scoped Crusher invitations |
| [Security](security.md) | Principals, secrets, isolation and exposure |
| [Releases](releases.md) | CI, immutable artifacts, saved-copy updates, rollback and publication gates |
| [Verification status](IMPLEMENTATION.md) | Dated evidence and outstanding qualification |
| [Dependency remediation](dependency-remediation.md) | Unresolved image security findings and required fresh scans |

## Maintaining the documentation

Keep one owner for each contract: product scope in Requirements, topology in
Architecture, operation details in the relevant guide, and evidence in the verification
records. Link to that owner instead of copying its procedure. Distinguish required,
implemented, locally tested and deployed behavior. Use dates and source/artifact
identities for claims about a test or stand.

Operator-facing article content is maintained separately in
[documentation.py](../src/mastermind/documentation.py). A behavior change must update
those articles and their navigation/search metadata as well as the relevant technical
guide. Reorganizing these Markdown files alone does not change the in-app guide.

[Decision records](acceptance-decisions.md) preserve scoped owner decisions.
Superseded designs, original requirements and old qualification reports are kept in
[history](history/README.md), outside the active guide list. Historical instructions
must not be used as current deployment or release procedures.
