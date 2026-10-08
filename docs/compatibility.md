# Compatibility and integrations

Mastermind's Core, Runtime, Worker, managed Bridge, database schema and local
models form one signed compatibility group. Current pins live in
[component-lock.json](../component-lock.json), [embedding-model.lock.json](../embedding-model.lock.json),
[curator-model.lock.json](../curator-model.lock.json) and the dependency lockfiles.
Use those values rather than a historical prose version list.

## Producer responsibilities

| Producer | Mastermind contract |
| --- | --- |
| Kernel / Volt | Authorized Register discovery and exact Shell-secret resolution; references belong in Register, resolved values stay out of logs/backups |
| Chronos | Separate scoped event-card reader and monthly report writer; neither authorizes general Vault access |
| Saturn / Neptune | Declared recovery archive and/or Vault mirror, separately scoped mirror resource reader, bounded Range access and verified transfer receipts |
| Updater | Host dependency installation, own-head three-image update, saved-copy protocol 2, scoped enrollment and verified recovery |
| Gryphon | Paired stable Telegram identity, authenticated command delivery and scoped Crusher invitations |
| Wyvern | Allowed Adapter/function bindings, provider transport and credentials; Mastermind owns prompts, budgets and output validation |

Mastermind never receives permanent Saturn credentials. Its owner resource API uses
the distinct Neptune reader, validates project/purpose/subtree and streams bounded
content. Public Shared and Crusher identities cannot use it. There is no direct
Saturn fallback or second Neptune daemon. Archive-only enrollment grants no mirror
reader; mirror-only enrollment cannot execute archive operations.

Core verifies exported size, SHA-256 and generation; Neptune acknowledges only
after a verified Saturn receipt or complete mirror reconciliation. A lost archive
acknowledgement reuses its durable run/idempotency key. Mirror retries take a fresh
complete snapshot; incomplete listing/export cannot authorize deletions. Selected
pipelines retain independent execution and receipts. Settings owns schedule intent;
paired profiles commit one enabled state and hourly interval atomically.

## Discovery, identities and enrollment

Service origins are resolved through authorized Kernel bindings. Updater's own host
machine identity owns shared-component release discovery; an application head or
operator Access Key is not that authority. Root TUI fallback sources apply only
when its Kernel connection is unavailable, never after authorization or integrity
failure. Default Mastermind installation ensures Updater, Neptune, Gryphon and local
Wyvern under [central Part 13](https://github.com/psewdon1m-exocortex/general/blob/main/PART_13_HOST_DEPENDENCIES_AND_EXTENSION_GUIDE.md).

For Chronos event references, bind `services.mastermind.secrets.chronos_service_token`
and `services.chronos.mastermind_reader_token` to the same Volt field, permitting
each principal only its own key. Chronos resolves its expected token fresh in memory.
Existing explicit file enrollment remains a migration path. Monthly reports use a
separate `services.mastermind.secrets.chronos_report_token`; see [Deployment](deployment.md).

Gryphon adapter registration and one-time `/link CODE` owner pairing occur in
`sudo updater tui`. Mastermind selects the paired adapter and receives only its
scoped binding. Gryphon status must supply the stable connection/user/chat identities;
older incompatible gateways cannot issue invitations. See [Gryphon](gryphon.md).

Wyvern Adapters and client grants are managed in the host TUI. Mastermind selects
allowed `text` and `media` bindings. `services.wyvern.management_url`, when present,
must resolve to an existing authorized HTTPS management interface; the daemon has
no implicit standalone web administration. Without a configured destination,
report configuration required. Restored binding/schedule intent remains pending
until the matching external identity and revision are verified. Resolved provider
secrets are never included in that intent.

## Source candidates versus published compatibility

[compatibility.json](compatibility.json) preserves the exact September producer
baselines, exported patch hashes and qualification status. Its `published: false`
value is a release blocker. The baseline versions in that record are not today's
recommended releases. Later producer work resides in the producer repositories;
do not reapply the historical patches over newer trees or attribute their behavior
to an unqualified published version.

Before publication, identify the actual immutable producer artifacts, run their
own checks and the consumer integration suite, then update dependency versions and
digests together. Saved-copy updates require `mastermind.saved-copy.v2` on Updater
and compatible signed protocol fields on source/target Mastermind releases.
Both installation orders, shared singleton reuse, scoped unlink, update and rollback
require actual host qualification. Producer source existence alone does not pass.

Unit stubs are fault/protocol evidence. Isolated real producer/container tests,
native Obsidian, public DNS/TLS and live provider/Telegram tests have separate
acceptance boundaries. [Verification status](IMPLEMENTATION.md) and
[Conformance](conformance.md) identify the recorded evidence and gaps; no current
live integration is inferred from an old local checkpoint.
