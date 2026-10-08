# Documentation authority and maintenance

Reviewed against the workspace `.docs` on **2026-10-06**. Central
[Part 00](https://github.com/psewdon1m-exocortex/general/blob/main/PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md)
is authoritative. In this workspace it is `exocortex/.docs`; the links below address
the separate `psewdon1m-exocortex/general` repository so this checkout remains usable
on its own. A local uncommitted central decision may not yet appear at those URLs.

Central rules take precedence over project guides. Explicit, scoped owner decisions
remain applicable to their subject; an old project specification or a historical
PASS cannot waive a newer central contract. [Conformance](conformance.md) records
implementation gaps without redefining them as supported alternatives.

## Applicability map

| Central authority | Mastermind application and guide |
| --- | --- |
| [Part 00](https://github.com/psewdon1m-exocortex/general/blob/main/PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md) | Authority, impact review and divergence handling; this document and Conformance |
| [Part 01](https://github.com/psewdon1m-exocortex/general/blob/main/PART_01_INTERFACE_AND_INTERACTION_UNIFICATION.md) | Owned Shell and public UI; Operations, Sharing and Public Shared presentation. The native Obsidian viewport retains its approved UI exception. Node-canvas project editing is not a Mastermind feature. |
| [Part 02](https://github.com/psewdon1m-exocortex/general/blob/main/PART_02_OBSERVABILITY_AUDIT_AND_LOG_EXPORT.md) | Bounded logs, audit and export; Operations and Security |
| [Part 03](https://github.com/psewdon1m-exocortex/general/blob/main/PART_03_BACKUP_AND_RECOVERY.md) | Mandatory state, archive lifetime, restore and update copies; Backup and restore, Releases |
| [Part 04](https://github.com/psewdon1m-exocortex/general/blob/main/PART_04_BOOTSTRAP_AND_DEPLOYMENT.md) | Bootstrap, host prerequisites, secret files and health; Deployment |
| [Part 05](https://github.com/psewdon1m-exocortex/general/blob/main/PART_05_CI_RELEASES_AND_LOCAL_UPDATES.md) | Versioning, CI, signed releases and update/rollback; Releases |
| [Part 06](https://github.com/psewdon1m-exocortex/general/blob/main/PART_06_UNIFIED_ACCEPTANCE_CHECKLIST.md) | Cross-domain acceptance and seven-area pre-push review; Verification status |
| [Part 07](https://github.com/psewdon1m-exocortex/general/blob/main/PART_07_SECURITY_AND_EXPOSURE_CONTROL.md) | Identity, source/image secrets, ingress and private exposure; Security and exposure inventory |
| [Part 08](https://github.com/psewdon1m-exocortex/general/blob/main/PART_08_SEO_AND_GEO.md) | Public/indexable profile is N/A: Mastermind exposes no indexable content. Classification and non-indexable/private checks still apply. |
| [Part 09](https://github.com/psewdon1m-exocortex/general/blob/main/PART_09_SERVICE_AGENTS_DEPLOYMENT_AND_LIFECYCLE.md) | Shared-agent ownership, enrollment, service-owned schedules and TUI lifecycle; Compatibility, Deployment and Gryphon |
| [Part 10](https://github.com/psewdon1m-exocortex/general/blob/main/PART_10_SERVICE_AGENTS_UI_AND_OPERATOR_WORKFLOWS.md) | Backup, Updates, Gryphon and Wyvern Settings workflows; Operations, Backup and Releases |
| [Part 11](https://github.com/psewdon1m-exocortex/general/blob/main/PART_11_INITIAL_MULTI_SERVICE_DEPLOYMENT.md) | Reference deployment profile; this documentation task does not deploy that topology |
| [Part 12](https://github.com/psewdon1m-exocortex/general/blob/main/PART_12_KNOWN_DEPLOYMENT_AND_OPERATIONS_PROBLEMS.md) | Complete known-problem qualification on the exact outgoing release candidate |
| [Part 13](https://github.com/psewdon1m-exocortex/general/blob/main/PART_13_HOST_DEPENDENCIES_AND_EXTENSION_GUIDE.md) | Mastermind ensures Updater, Neptune, Gryphon and default local Wyvern; shared-agent release authority belongs to the host |

The 2026-10-05 [synchronization enrollment decision](https://github.com/psewdon1m-exocortex/general/blob/main/decisions/2026-10-05-synchronization-enrollment.md)
updates Parts 03, 09 and 10: Mastermind can enroll archive, mirror or both; the
resource reader accompanies mirror; paired schedules share one control. The Pluto
outdoor exception applies only to Pluto and does not remove Mastermind dependencies.

## External policy reference and release evidence

The owner requested removal of `docs/policy` on 2026-10-06. Central prose and visual
assets are no longer copied into Mastermind. [policy-lock.json](policy-lock.json)
now records the central repository, immutable baseline revision and Part 12 digest
needed for reproducible evidence verification. It is not a competing source of rules.

The reference is deliberately **publication_ready: false**. The central checkout
contains newer uncommitted decisions, and current conformance gaps have not been
closed by this documentation work. Updating links or reading a pinned catalog must
not lift the release gate. Before publication, adopt the required central changes
in an immutable revision, update its digest, resolve the applicable gaps and collect
new qualification before explicitly changing that readiness field.

Verification reads the locked commit through `--central-checkout` or
`MASTERMIND_POLICY_CHECKOUT`. The sibling `.docs` Git checkout is used automatically
when present. Its working-tree edits do not alter pinned evidence. In an isolated
checkout, only the pinned Part 12 file is fetched from the fixed official repository
over HTTPS with a size limit and SHA-256 verification. Network, revision or digest
failure fails the check; there is no fallback to changing `main` or cached acceptance.
This is build/verification behavior, not a production runtime dependency.

```text
python scripts/validate_repository.py --central-checkout ../.docs
python scripts/known_problems_gate.py catalog --central-checkout ../.docs --output artifacts/catalog-check.json
```

For a documentation-only revision, check the root inventory, links, archived paths
and packaging consumers. Changes to policy loading additionally require the release
gate's positive and negative tests. A push still needs the seven-area record in
[Releases](releases.md); local document validation is not release qualification.
