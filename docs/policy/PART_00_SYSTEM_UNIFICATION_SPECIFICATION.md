# Part 00. System Unification Specification — Documentation Authority And Orchestrator

This document is the entry point and authority index for the engineering guides
stored in `.docs`. It tells an implementer which documents apply, how to
sequence the work, which evidence to collect, when operator approval is
required, and how to prove completion.

Detailed requirements live in Parts 01–11 linked below. Together those files
are the workspace-wide source of truth. This orchestrator does not weaken,
summarize away or replace their normative rules.

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT** and **MAY** are
normative. Numeric defaults may change only after workload measurement, while
the safety property behind every limit MUST be preserved.

## 1. Mandatory Material-Divergence Protocol

During implementation, compare every applicable guide with the behavior that
already exists in the target project. A difference is **material** when it
changes observable behavior, UI or UX, accessibility, a data or API contract,
persistence, security or trust boundaries, limits, deployment, update or
recovery behavior, compatibility, search visibility, machine-readable output,
or operator workflow.

Project-local documentation never overrides `.docs`. When a project README,
runbook, concept, ADR, embedded Documentation article or other local document
conflicts with an applicable central rule, the central rule wins and the local
document MUST be corrected. A project-local document MAY add concrete names,
paths, ports and operational details only when they remain compatible with the
central contract.

Existing runtime behavior is evidence rather than a competing documentation
authority. When code, configuration, deployed behavior or a required migration
cannot immediately satisfy an applicable central rule, the difference remains
material and MUST be reported before the affected implementation is changed.

When a material difference is found, the implementer MUST:

1. pause the affected decision while continuing only independent work that
   cannot prejudice the decision;
2. notify the operator before implementing the divergent behavior;
3. provide a material-divergence report using the template below;
4. ask the operator explicitly whether to implement the central rule directly,
   use a staged compatibility path or amend `.docs` through an explicit central
   documentation decision;
5. record the decision and rationale before resuming the affected work;
6. update the implementation plan, acceptance criteria and rollback plan to
   reflect the decision.

Silence is not approval. If the difference exposes an immediate security,
data-loss or de-indexing risk, report it as urgent and avoid destructive
action; make only previously authorized, reversible containment changes until
the operator decides.

### 1.1 Required Material-Divergence Report

```text
Material divergence: <short title>

Applicable guide:
- document and section:
- normative rule:

Observed implementation:
- behavior:
- evidence: <files, lines, configuration, tests or runtime observations>

Difference:
- exact mismatch:
- why it is material:

Impact:
- users and operator workflow:
- data and compatibility:
- security and operations:
- migration and rollback:

Options:
1. implement the current central rule directly;
2. use a staged compatibility or migration path that converges on it;
3. amend `.docs` through an explicit central documentation decision;
4. another evidence-backed convergence option, if needed.

Recommendation:
- preferred option and reasons:
- verification required:

Operator decision requested:
- Which option should be implemented?
```

## 2. Document Map

| Document | Primary scope | Apply when |
| --- | --- | --- |
| [Part 01. Interface And Interaction Unification](./PART_01_INTERFACE_AND_INTERACTION_UNIFICATION.md) | UI foundations, linked visual-reference templates, interaction, navigation, universal cards, dashboards, settings, collection toolbars, node canvases, dependency graphs, responsive behavior and accessibility | The system has an operator or end-user interface |
| [Part 02. Observability, Audit And Log Export](./PART_02_OBSERVABILITY_AUDIT_AND_LOG_EXPORT.md) | Structured events, redaction, retention, disk and RAM limits, log views and secure downloads | The system emits, stores, displays or exports logs or audit events |
| [Part 03. Backup And Recovery](./PART_03_BACKUP_AND_RECOVERY.md) | Backup scope, exclusions, archive integrity, restore transactions and recovery testing | The system owns authoritative or operator-managed state |
| [Part 04. Bootstrap And Deployment](./PART_04_BOOTSTRAP_AND_DEPLOYMENT.md) | One-command preparation, environment contract, installer behavior, deployment security and health verification | The system is installed or operated outside a developer workstation |
| [Part 05. CI, Releases And Local Updates](./PART_05_CI_RELEASES_AND_LOCAL_UPDATES.md) | Version model, CI and release tag namespaces, build gates, artifacts, release discovery, privileged updater, rollback and supply-chain controls | The system publishes releases or updates installed software |
| [Part 06. Unified Acceptance Checklist](./PART_06_UNIFIED_ACCEPTANCE_CHECKLIST.md) | Mandatory pre-push integrity/documentation gate, cross-domain acceptance and final definition of done | Always; every push records `PASS` evidence or a reasoned `N/A` for each required pre-push area |
| [Part 07. Security, Secret Handling And Exposure Control](./PART_07_SECURITY_AND_EXPOSURE_CONTROL.md) | Mandatory pre-push security review, secret-safe CI and deployment, release provenance, runtime isolation, private/concealed exposure, crawler policy and automated-probe resistance | Security review is always required; private/concealed checks additionally apply to every surface with that exposure mode |
| [Part 08. SEO And GEO Engineering](./PART_08_SEO_AND_GEO.md) | Conditional pre-push visibility review, indexable HTML, metadata, structured data, discovery, feeds, agent interfaces, public-content generation and search observability | The product has public, intentionally indexable content or an explicit maximum-discovery objective |
| [Part 09. Service Agents: Deployment, Initialization And Lifecycle](./PART_09_SERVICE_AGENTS_DEPLOYMENT_AND_LIFECYCLE.md) | Concrete Updater, Neptune and Gryphon topology, installation, enrollment, control, update and recovery contracts | A module deploys, initializes or operates a shared host agent |
| [Part 10. Service Agents: UI And Operator Workflows](./PART_10_SERVICE_AGENTS_UI_AND_OPERATOR_WORKFLOWS.md) | Concrete backup, messaging connection, updates and synchronization panels, states, controls and linked visual templates | A module exposes shared-agent status or actions |
| [Part 11. Initial Multi-Service Deployment Profile](./PART_11_INITIAL_MULTI_SERVICE_DEPLOYMENT.md) | Concrete coordinated deployment, trust, recovery and acceptance profile for the initial service set | Deploying or validating that explicitly named service topology |
| [Part 12. Known Deployment And Operations Problems](./PART_12_KNOWN_DEPLOYMENT_AND_OPERATIONS_PROBLEMS.md) | Stable cross-service problem IDs, recurring deployment/operations failure classes, durable remediation and the mandatory known-problem release gate | Every service-qualified release and every incident/regression that reveals a reusable failure class |

## 3. Source-Of-Truth Rules

- `.docs` is the documentation root of truth for the entire workspace. The
  linked Parts are normative for their stated scope and take precedence over
  every project-local README, runbook, concept, ADR and embedded Documentation
  article.
- A project-local document MUST link to the applicable central Part, translate
  its generic roles into current project-specific values and remain no less
  strict. Conflicts are fixed in the project document; they are not resolved by
  selecting the older local rule.
- Active documentation MUST use the current service name, repository address,
  default branch, tag namespace, release process and CI workflow. Superseded
  project codenames, moved repositories, retired `dev`/`stage`/`prod` branch
  models, dead document targets and compatibility files with no remaining
  consumer MUST be removed rather than left as apparently normative guidance.
  Intentionally retained history MUST be clearly marked non-normative and kept
  outside the active documentation index.
- Parts 01–08 use role names and placeholders deliberately. Product names,
  concrete tags and concrete filesystem paths belong only in a product's own
  runbook or an explicitly scoped deployment-profile document; such examples
  MUST NOT silently become a universal convention for other services.
- PNG assets in [`./src`](./src/) become normative visual references only where
  Part 01 links and describes them. Part 01's written tokens, behavior,
  accessibility and responsive rules take precedence over incidental
  anti-aliasing, crop and one-pixel rounding in those raster exports. Example
  names, icons and data remain placeholders unless the text says otherwise.
- This orchestrator is normative for document selection, evidence, divergence
  handling, approval and final handoff.
- Part 06 integrates the other unification parts but does not replace their
  detailed acceptance criteria.
- Part 12 is a derived problem and regression registry. Its stable IDs and
  release-evidence gate are normative, while Parts 01–11 remain authoritative
  for the underlying engineering requirement. A catalog entry cannot waive or
  weaken the Part from which it is derived.
- Part 07 is the common security baseline. A more permissive SEO/GEO discovery
  rule applies only to routes deliberately classified as public; it never
  weakens authentication, private-network or secret-handling requirements.
- Browser-based operator applications use the `public authenticated` profile:
  the sign-in surface is reachable from every client IP, while Access Key
  verification, application sessions and route authorization protect all
  operator data. `OPERATOR_CIDR` and equivalent source-IP admission settings
  are not part of the architecture.
- An Access Key is a required, operator-supplied opaque exact value. "Required"
  means that the operator must explicitly supply a value; it is not a password
  policy. A service MUST NOT impose an Access-Key-specific minimum or maximum
  length, strength or entropy score, required or forbidden character class,
  URL-safe/ASCII-only rule, dictionary/breach/example/placeholder denylist,
  trimming, Unicode normalization or case folding. Bootstrap, sign-in, rotation,
  backup/restore and offline-unlock paths MUST preserve and compare the same
  value exactly. A missing value remains an invalid unconfigured state.
- Public HTTP(S), WebSocket routing and TLS belong to one server-managed Nginx.
  A service MUST NOT bundle or operate its own Nginx. coturn is not a baseline
  component; a genuine WebRTC NAT-traversal requirement needs a project-specific
  decision because that transport cannot be replaced by an Nginx proxy rule.
- Every independently versioned service starts at `0.0.1` and follows the
  version/tag namespace in Part 05. A plain `v0.0.1`-style tag invokes CI only;
  only a service-qualified `service-v0.0.1`-style tag may invoke publication.
- Every deployable service owns a separate release `bootstrap.sh` and a separate
  `.env`. Protected GitHub Secrets hold its private release-signing key; release
  CI publishes only the derived public part, embedded in that bootstrap. The
  bootstrap provisions local release trust, verifies the signed manifest and
  only then downloads the service and creates its namespaced configuration.
- The default production sequence is operator-prepared server, exact versioned
  bootstrap, edit only marked operator inputs, mode-`0600` environment,
  install, status, loopback health, then operator-managed Nginx configuration
  and an external canonical-HTTPS check. A service-specific variation documents
  its reason without moving public ingress into the installer.
- Parts 09 and 10 are normative for the concrete shared-agent
  topology. Bot registration, service-function linking
  and Telegram identity binding remain separate trust decisions.
- The SEO and GEO guide is additive for public/indexable surfaces. It does not
  authorize a reduced alternate UI or an unapproved redesign.
- A requirement marked non-applicable MUST include a reason and evidence. It
  cannot be omitted merely because implementation is inconvenient.
- If two applicable rules appear incompatible, treat the conflict as a material
  divergence and request an operator decision. Do not resolve it silently by
  selecting the easier rule.
- Product-specific identifiers, paths, variable names and topology MUST remain
  in project documentation or an approved decision record, not be copied into
  the reusable Parts. The service-agent documents are the approved shared
  decision record for the concrete cross-project identifiers they enumerate.

## 4. Required Implementation Workflow

### 4.1 Establish Scope

1. Identify the deployable units, user-facing surfaces, authoritative data,
   inbound and outbound connections, secret flows, public/indexable/private
   routes, operational boundaries and update mechanisms.
2. Read this orchestrator and every document that may apply.
3. Create an applicability matrix before changing code.
4. Mark each document and major section as `applicable`, `not applicable`, or
   `requires investigation`.
5. Give every `not applicable` decision a concrete reason and evidence.

### 4.2 Record The Existing Baseline

Inspect code, configuration, CI workflows, tests, runtime behavior and current
operator documentation. Record at least:

- implemented behavior and defaults;
- security and privilege boundaries;
- data ownership, persistence and migrations;
- log, backup and download limits;
- bootstrap, deployment, release and update paths;
- CI identities, secret delivery, artifact provenance, network listeners,
  exposure modes and crawler/automation enforcement;
- external-provider credentials, runtime supervision, identity binding and
  revocation paths;
- UI/UX and accessibility behavior;
- public rendering and discovery behavior, when applicable;
- test coverage and known unverified assumptions.

The baseline is evidence, not an instruction to preserve every historical
choice. Its purpose is to expose material differences before implementation.

### 4.3 Build The Implementation Plan

Map each intended change to:

- an applicable guide section;
- current implementation evidence;
- acceptance tests;
- migration and rollback needs;
- required operator decisions;
- dependencies on other work.

Do not begin a change whose material divergence is waiting for an operator
decision. Independent, reversible work may continue.

### 4.4 Implement In Dependency Order

Use the following dependency order unless project evidence justifies another
order:

1. data, identity, security, exposure and trust-boundary contracts;
2. observability and bounded diagnostics;
3. backup creation, integrity and tested restore;
4. external-connection identity binding, user-facing behavior, accessibility
   and public rendering;
5. bootstrap and deployment automation;
6. CI artifacts, release publication and updater behavior;
7. cross-domain acceptance and recovery exercises.

This is a dependency model, not permission to batch unsafe changes. For
example, an updater MUST NOT be considered complete before the backup/restore
contract it depends on has been exercised.

### 4.5 Verify At The Correct Layers

Every implemented requirement MUST be consistent across:

1. configuration defaults;
2. runtime enforcement;
3. operator UI and documentation;
4. automated tests.

Use the narrowest useful tests during implementation, followed by relevant
integration, browser, packaging, restore, deployment and update checks. Verify
negative paths and enforced limits, not only successful examples.

### 4.6 Mandatory Pre-Push Change-Impact Gate

Before every branch or tag push, the author or responsible automation MUST
inspect the complete outgoing diff and evaluate all seven of these areas:

1. backup creation and restore;
2. service update, compatibility and rollback;
3. operator documentation rendered in the application's Documentation view;
4. technical documentation for every affected service and the workspace or
   repository root `README`;
5. security and trust-boundary integrity;
6. public/indexable SEO and GEO integrity when maximum discovery or promotion
   is in scope;
7. private/concealed exposure integrity when resources or pages are intended to
   be hidden from crawlers, agents, probes or the public Internet.

The evaluation itself is mandatory for every push. The work required by it is
impact-based: a documentation-only change may mark runtime checks not
applicable, while a state-schema, migration, deployment or updater change
requires the relevant profile tests. Security is always applicable and MUST
finish as `PASS`. Each other area MUST finish as either `PASS` or `N/A`:

- `PASS` identifies the changed document, enforcement point or test and records
  reproducible evidence from the exact outgoing revision;
- `N/A` identifies the inspected paths and explains concretely why the diff
  cannot affect that area;
- `UNKNOWN`, an unchecked item, a failed command, stale documentation or an
  unexplained `N/A` blocks the push.

The minimum impact review is:

| Area | Change triggers | Required result before push |
| --- | --- | --- |
| Backup and restore | New, renamed or removed persisted values; database/schema/migration changes; settings, files, identities, revisions, queues or ownership changes | Classify every affected value as mandatory, conditional, derived or forbidden; update export, manifest, import and compatibility behavior; exercise the required round trip and negative paths |
| Service update | Runtime, dependency, artifact, image, manifest, migration, configuration, bootstrap, health, backup handoff or rollback changes | Prove release/update contract compatibility, backup readiness, post-update health and rollback behavior at the depth required by Part 05 |
| Documentation view | Any operator-visible workflow, setting, action, permission, limit, failure mode, backup/restore or update behavior changes | Update the internal article source, navigation/search metadata and links; build or render the view and prove the changed material is findable and accurate |
| Technical documentation and root README | API, configuration, environment, port, dependency, security, deployment, migration, recovery, update, topology or development-command changes | Update every affected service's technical documentation and update the root README when its workspace-wide facts or entry-point instructions change |
| Security | Every push; deeper checks are triggered by code, dependencies, routes, listeners, identity, authorization, secrets, untrusted input, storage, CI, deployment, backup, update or policy changes | Record a security `PASS` from diff review and baseline scanning; for an affected boundary, update the threat/exposure model and exercise relevant positive and negative security tests |
| Public/indexable SEO and GEO | A public/indexable route, page type, template, content model, metadata, navigation, media, structured data, discovery file or lifecycle rule is added, changed or removed | Update the public page-type/URL registry and prove first-response HTML, metadata, discovery, structured data, link, lifecycle, accessibility, performance and UI/UX contracts; produce the SEO release diff |
| Private/concealed exposure | A private/concealed listener, route, page, hostname, edge rule, authentication surface, machine-navigation artifact or resource reference is added or changed | Prove default-deny/private reachability from an unauthorized external vantage point and prove the resource is absent from public discovery, documentation and artifacts; test bots/agents and forged identity claims |

Applicability is determined from versioned route, listener and page-type
registries. Every surface MUST be explicitly classified as `public/indexable`,
`public/non-indexable`, `private` or `concealed`. A service may activate both
conditional profiles for different surfaces, but one surface cannot be both
`public/indexable` and `concealed`. A missing classification is `UNKNOWN` and
blocks the push. Reclassification is a material exposure change and requires an
explicitly reviewed policy diff; it cannot be inferred from a menu, hostname,
`robots.txt` or `noindex` change.

The public SEO/GEO area may be `N/A` only when the classified system has no
`public/indexable` surface and no maximum-discovery objective. The
private/concealed area may be `N/A` only when it has no `private` or `concealed`
surface and no maximum-concealment objective. Once either conditional profile
is active, it MUST produce `PASS` on every push; an unrelated diff may reduce
the test depth, but its recorded no-impact review is `PASS`, not `N/A`.

A project MUST expose one reproducible pre-push verification command and SHOULD
wire it to a local Git `pre-push` hook. CI MUST repeat the machine-verifiable
subset and block merge, release or publication on failure; a bypassed local
hook is not evidence that the gate passed. Destructive or long-running tests
need not run for an evidenced `N/A`, but cost alone is not a reason to omit a
test required by an affected contract.

The detailed criteria live in [Part 01](./PART_01_INTERFACE_AND_INTERACTION_UNIFICATION.md),
[Part 03](./PART_03_BACKUP_AND_RECOVERY.md),
[Part 05](./PART_05_CI_RELEASES_AND_LOCAL_UPDATES.md) and
[Part 06](./PART_06_UNIFIED_ACCEPTANCE_CHECKLIST.md), with security and
concealment in [Part 07](./PART_07_SECURITY_AND_EXPOSURE_CONTROL.md) and
public discovery in [Part 08](./PART_08_SEO_AND_GEO.md).

### 4.7 Hand Off To The Operator

The final report MUST include:

- documents and sections applied;
- sections declared non-applicable and why;
- material-divergence reports and operator decisions;
- changed behavior and preserved behavior;
- migrations, compatibility boundaries and rollback instructions;
- exact verification performed and results;
- residual risks, untested assumptions and follow-up work.

## 5. Required Work Products

| Work product | Minimum content |
| --- | --- |
| Applicability matrix | Every document and major section, status, reason, evidence and owner |
| Baseline report | Current behavior, code/config/runtime evidence, defaults and known gaps |
| Material-divergence report | Rule, evidence, mismatch, impact, options, recommendation and explicit operator decision |
| Implementation plan | Ordered changes, dependencies, acceptance tests, migration and rollback |
| Verification matrix | Requirement mapped to enforcement point and test result |
| Pre-push impact record | Outgoing revision, seven required areas, exposure classifications, `PASS` evidence or reasoned `N/A`, commands and results |
| Exposure and connection matrix | Every listener, route and external provider; mode, identity, secret source, policy, owner, revocation and external-vantage test |
| Operational handoff | Deployment, monitoring, backup, restore, update, rollback and known limitations |

These artifacts may live in the project's normal planning and decision system;
they do not have to be added to this reusable specification repository.

## 6. Cross-Document Completion Gate

Implementation is complete only when:

- every relevant document was evaluated through the applicability matrix;
- every material difference was reported and explicitly decided by the
  operator;
- decisions are reflected in code, configuration, tests and operator
  documentation;
- configured limits are enforced at runtime;
- backup and restore were exercised with realistic state;
- deployment health checks and failure diagnostics were exercised;
- release/update rollback was tested when updates are in scope;
- every outgoing push passed the seven-area pre-push impact gate with evidence;
- CI/deployment secret boundaries and external reachability were tested from
  the applicable trusted and untrusted vantage points;
- Messaging-gateway bot registration, service-function linking, one-time provider-user
  binding, authorization and scoped revocation were tested when such a
  connection is in scope;
- public source HTML, metadata and discovery were tested when SEO/GEO is in
  scope;
- applicable Part 06 items pass, and exclusions contain evidence;
- the final handoff identifies residual risks without presenting assumptions
  as verified guarantees.

A displayed but unenforced limit is not complete. A backup never restored is
not a recovery mechanism. A checksum without a trusted source is not publisher
authentication. A started process that failed its health contract is not a
successful deployment. An unreported material divergence is not an accepted
implementation decision.
