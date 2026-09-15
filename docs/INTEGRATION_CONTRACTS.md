# Mastermind integration work

The final service requirements §§139–141 and workspace `.docs` remain authoritative. This file records implementation locations and qualification boundaries; it does not declare the required new producer APIs already released.

| Producer | Released baseline | Local worktree | Required change |
| --- | --- | --- | --- |
| Neptune | neptune-v0.1.7 | ../.local/services/neptune | Scoped owner resource listing, metadata and bounded Range reader; archive/mirror receipts and enrollment qualification |
| Saturn | saturn-v0.1.15 | ../.local/services/saturn | Read-only service resource capability, paginated reader and conditional streaming; typed Mastermind enrollment qualification |
| Updater | updater-v0.4.7 | ../.local/services/updater | Sealed streaming backup spools and fixed Mastermind component-group profile; reader credentials during enrollment |
| Kernel | kernel-v0.2.10 | ../.local/services/kernel | Real Register/discovery and shell-secret contract qualification |
| Volt | volt-v0.1.5 | ../.local/services/volt | Real secret resolution/rotation/recovery qualification |
| Chronos | chronos-v0.1.1 | ../.local/services/chronos | New minimal event-reader capability for owner cards; separate token, purpose and Kernel discovery |

Core never receives permanent Saturn credentials. Neptune's reader uses a distinct read-only credential and validates the project, purpose and canonical logical subtree before contacting Saturn. Public Shared/Crusher identities cannot enter the owner resource paths. The mirror credential remains scoped to the dedicated Mastermind root and is distinct from the recovery archive credential.

Local integration tests will run the actual service code in isolated containers/volumes with generated test identities and local TLS. Stub transports are limited to unit/fault-injection checks and are not reported as integrated-service PASS. Host production checks and producer-release qualification retain their own evidence status.

The local Neptune candidate also validates Core export size/SHA-256/generation before upload, persists archive generation with the durable run, declares Mastermind encryption per run, and acknowledges Core only after the Saturn receipt or verified mirror reconciliation. A lost archive acknowledgement retries the same durable run/idempotency key. Mirror retries take a fresh complete snapshot; an incomplete export/listing never authorizes deletion. These contracts require new qualified producer releases before a production Mastermind manifest may advertise them.
