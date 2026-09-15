# Part 05. CI, Releases And Local Updates

> This is a normative component of the [Part 00 documentation authority](./PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md).

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT** and **MAY** are
normative. Numeric defaults may change only after workload measurement, while
the safety property behind every limit MUST be preserved.

## Central Authority And Material Divergence

This Part takes precedence over conflicting project-local documentation.
Project documents MUST adapt these rules to current project-specific values
without weakening them. A material implementation difference follows the
reporting and decision protocol in [Part 00](./PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md#1-mandatory-material-divergence-protocol); stale local documentation is corrected and is not an alternative authority.

---
## 24. Responsibility Boundaries

Keep these roles separate:

- CI turns a tagged source revision into immutable release artifacts.
- A protected release-signing job receives only that service's private key from
  GitHub Secrets, signs the release manifest, derives the public counterpart and
  embeds only that public part in the service's release `bootstrap.sh`.
- A control-plane registry distributes repository locations and compatibility
  policy.
- The application exposes the operator workflow, creates a logical backup and
  submits only a desired version to the local updater.
- The privileged updater independently resolves and verifies that version,
  owns the container-engine boundary and mutates only services registered on
  its host.
- A portable client validates a separately signed update contract because it
  runs outside the server-host trust boundary.

The web application MUST NOT receive the container-engine socket. It MUST NOT
send an arbitrary command, image or release URL to the updater.

## 25. CI Trigger And Pipeline Shape

### 25.1 How Release Pipelines Start

Each deployable module has its own repository and release workflow. An embedded
dependency is consumed as a version-pinned, checksummed published asset rather
than from a sibling checkout.

Every independently versioned service uses the numeric
`MAJOR.MINOR.PATCH` model. Its first releasable version is `0.0.1`; `0.0.0` is
reserved for unreleased or development state and MUST NOT be published. Numeric
components contain no leading zero unless the component is exactly `0`.

- `PATCH` increments for compatible fixes and documentation/package corrections;
- `MINOR` increments for compatible functionality or an explicitly documented
  pre-1.0 contract change;
- `MAJOR` increments for an intentionally incompatible stable contract.

Two non-overlapping tag namespaces are mandatory:

| Tag | Example | Required effect |
| --- | --- | --- |
| Plain validation tag | `v0.0.1` | Starts verification-only CI for that revision. It MUST NOT publish a release, receive a release-signing secret, create or move a release alias, or upload production artifacts. |
| Service release tag | `service-v0.0.1` | Starts that service's release pipeline. The service slug is the current lowercase repository/service identifier. Release publication is blocked until the same revision passes the complete CI and pre-push gate. |

A plain tag and a service-qualified tag are never aliases for one another. A
release workflow MUST match only its exact service prefix and MUST reject an
empty, foreign or malformed prefix. The manifest version is derived from the
qualified tag, the published release remains attached to that immutable tag,
and rerunning a workflow MUST NOT reinterpret or move an existing tag.

Ordinary pushes to the default `main` branch and pull requests run CI without
publication. A service release tag may invoke the same reusable CI workflow as
a prerequisite, but only its protected release job receives signing secrets and
publishes artifacts. Manual release publication is outside the baseline unless
an explicit recovery procedure preserves the same immutable tag, approval and
evidence contract.

### 25.2 Fail-Closed Build Chain

1. Check out the tagged revision and select the pinned toolchain major.
2. Derive and validate the version from the tag.
3. Validate shell entry-point syntax.
4. Install dependencies from lock or requirements files.
5. Run tests, compilation and type checking.
6. Fetch cross-repository dependencies at pinned versions and verify their
   SHA-256 files before extraction or embedding.
7. Build a release candidate and run profile-specific smoke tests.
8. Build the final OCI image or package and resolve its immutable digest.
9. Build checksummed installation bundles and the complete narrow release
   manifest.
10. Run the Part 12 pre-signing phase for catalog integrity, applicability and
    every check that does not depend on final signatures. Any unresolved result
    stops before release secrets are exposed.
11. In a protected release-only job, load this service's private signing key
    from GitHub Secrets, sign the canonical manifest and derive its public key.
12. Generate this service's standalone `bootstrap.sh` with the public key
    embedded; verify that no private-key bytes enter the bootstrap, bundle,
    image, cache, log or artifact set.
13. Verify the detached manifest signature and every artifact digest using the
    generated bootstrap/public-key outputs.
14. Generate provenance attestations; request an SBOM and provenance for OCI
    builds.
15. Complete the final [Part 12 known-problem release phase](./PART_12_KNOWN_DEPLOYMENT_AND_OPERATIONS_PROBLEMS.md#обязательный-проверочный-gate-перед-релизом)
    for signature/trust/provenance-dependent checks and retain
    `known-problems-report.json`.
16. Publish all artifacts under the original immutable version tag.

Any failed step prevents publication.

### 25.3 Tests By Module Profile

| Profile | Build and test gates | Published form |
| --- | --- | --- |
| Static host daemon | Shell syntax, all language package tests, static target build with version/build ID | Native package, install archive, manifest and SHA-256 files |
| Web/API head | Deterministic package install, API/security tests, type check, production UI build, browser end-to-end tests, container health smoke test | OCI image by digest, Compose archive, release manifest |
| API head with database | Installer syntax, dependency install, migration-head validation, full integration suite, embedded dependency checks, database/cache/API health smoke tests | OCI image by digest, Compose archive, release manifest |
| Head with separate web UI | Database-backed server suite, frozen UI install, UI unit tests and production build, container health smoke test | OCI image by digest, Compose archive, release manifest |
| Portable desktop client | Third-party runtime version/URL/SHA verification, unit tests, portable build, signed-manifest generation and verification tests | Executable, SHA-256, signed discovery manifest, public key |
| Local updater daemon | All package tests and static target build | Binary, native package, install archive, manifest and SHA-256 files |

Behavioral coverage demonstrated by the reference suites includes:

- configuration round trips, refusal of arbitrary shell jobs, queue
  idempotency, redaction, enrollment, certificate handling, approval forwarding
  and post-execution secret disposal for a host daemon;
- separate per-service registry profiles, safe identifiers, API token checks,
  local-host enforcement, socket collision, backup checksum enforcement,
  request idempotency, atomic image/version persistence, health rollback,
  minimum updater version and download-size limits for the updater;
- production-secret validation, authenticated APIs, revision checksums,
  backup/restore, release discovery, updater handoff, navigation, restore and
  responsive browser flows for web heads;
- password hashing, rate limiting, migrations, last-known-good policy,
  signed-client caching, tamper rejection, identity revocation and bounded logs
  for the larger control plane;
- session security, protected dashboards and formatting/category behavior for
  the scheduling profile;
- canonical JSON, signed heartbeat or identity data, device-bound protected
  storage, navigation policy, checksum staging and release-manifest validation
  for the portable client.

One important boundary remains: a locally built candidate is smoke-tested and
the registry image may then be built again. The pipeline does not necessarily
promote the exact tested image object. Reproducible inputs reduce this risk but
do not prove byte identity. The stronger design builds once, tests that digest
and promotes the same digest.

### 25.4 Pre-Push Update-Compatibility Audit

Before every branch or tag push, inspect the outgoing diff for effects on the
service update path. The audit covers runtime dependencies, images and
packages, release manifests, migrations, configuration/schema versions,
bootstrap and service definitions, updater APIs, backup handoff, health checks,
timeouts, job persistence and rollback. The audit itself is mandatory even
when the result is `N/A`.

An affected push cannot pass until evidence demonstrates, as applicable:

1. release and update manifests still describe the exact candidate artifacts,
   immutable digests, compatibility range and minimum updater version;
2. configuration and data migrations accept every supported source version or
   reject it before mutation with a clear compatibility result;
3. the updater verifies a fresh backup before mutation and any changed state is
   covered by the [Part 03 pre-push backup-scope audit](./PART_03_BACKUP_AND_RECOVERY.md#171-pre-push-backup-scope-audit);
4. installation starts the intended candidate and the declared health contract
   succeeds within its bounded timeout;
5. a failed health or migration path restores the previous runtime/version and,
   when data changed, restores the verified logical backup;
6. the web application still cannot supply arbitrary artifact URLs, images or
   commands to the privileged updater;
7. operator-facing update status, compatibility and recovery instructions are
   synchronized in internal and technical documentation.

Changes to migrations, backup/update contracts, manifest structure, updater
handoff, service definitions or health/rollback behavior require an update from
the oldest supported source version to the outgoing candidate and an exercised
rollback failure path. A `PASS` records exact commands, source/candidate
versions and results. `N/A` names the inspected paths and explains why the diff
cannot affect discovery, packaging, installation, health or rollback.

### 25.5 Known-Problem Regression Gate

Every service-qualified release MUST evaluate every active ID in
[Part 12](./PART_12_KNOWN_DEPLOYMENT_AND_OPERATIONS_PROBLEMS.md) against the
exact tagged revision and candidate artifact set. This gate runs after the
profile-specific build, tests and smoke checks have produced evidence, and
before the protected publication job may finalize the release.

The gate has a pre-signing phase and a final signed-artifact phase. The first
validates the catalog, classification and every check that does not need the
release signature; a failure prevents access to signing secrets. Only checks
whose evidence inherently depends on the final signature, derived public key,
bootstrap or provenance continue in the protected job, and they must pass
before publication.

The pipeline requires exactly one `PASS` or reasoned `N/A` for every active ID
and emits `known-problems-report.json` with
the service, full service revision, qualified tag, immutable central-documentation
revision and SHA-256 of the exact catalog bytes. A missing/stale report,
duplicate or omitted ID, `FAIL`, `UNKNOWN`, or
unsupported `N/A` blocks the next privileged stage. Evidence references
immutable job outputs, reports or exact commands; prose asserting that a
problem is fixed is not evidence.

Default-branch and plain validation-tag CI run catalog lint plus every
machine-verifiable affected check without release permissions. The qualified
tag reuses those results only when they belong to the identical revision and
then completes the full release-scope evaluation. Checks needing real
production inputs remain in deployment readiness; the release may prove the
template, fail-closed validation and operator runbook but MUST NOT report the
external production result as passed.

## 26. Release Artifact Contract

A server release manifest is an installation contract, not release notes.

`known-problems-report.json` is required companion release evidence. It is
bound to the exact service revision, service-qualified tag, immutable central
documentation revision and Part 12 catalog digest, published with the release
evidence/provenance set and retained for at least the supported lifetime of
that version. It is not a bootstrap trust input and never contains secrets or
private production coordinates.

| Generic field | Purpose |
| --- | --- |
| Schema version | Reject a contract the installer cannot understand |
| Component role and version | Bind the manifest to the selected tag and target |
| Image reference and digest | Form the immutable registry pull target |
| Bundle URL and SHA-256 | Bind the installation archive to exact bytes |
| Minimum updater version | Prevent an incompatible privileged update |
| Database schema generation | Declare migration compatibility information |
| Release notes URL | Give operator context without becoming a trust input |

The portable-client manifest additionally contains exact artifact URL,
SHA-256, byte size, channel, semantic version, API compatibility and minimum
controller version. It is signed over canonical JSON with an asymmetric key;
the signature field itself is excluded from the signed payload.

Each service owns a distinct private signing key stored only as a protected
GitHub Secret. It is exposed only to the release signing step, never to pull
request or ordinary branch CI. That step exports only the public counterpart
and embeds it directly in the same service's versioned `bootstrap.sh`; it is not
published as a standalone trust-on-first-use key asset. The private key is never
uploaded, cached, printed, added to an image layer or copied to a deployment
host.

On first installation, the bootstrap writes the embedded verifier to
`/etc/exocortex/release-trust/<service>.pem`. A service-specific technical
contract may declare one additional legacy compatibility path, written from the
same embedded verifier. Bootstrap then verifies the manifest signature before
following release URLs. Distribution does not use `scp`, a separately supplied
fingerprint or manual public-key preparation.

Rotation for an existing host is a signed trust transition: a manifest accepted
by the current key introduces the next public key, both keys overlap for a
bounded release window, and only then may releases require the new key. A new
bootstrap alone MUST NOT overwrite an existing non-matching trust anchor.

## 27. Release Discovery And Data Provenance

The operator's update check is informative. The privileged updater resolves
the release independently and does not trust the UI response.

1. The application authenticates to the control-plane configuration registry.
2. It validates snapshot schema, revision and checksum and stores a
   last-known-good copy.
3. It reads the repository location from a namespaced registry entry.
4. It queries the hosted release API and displays installed and available
   versions.
5. On installation, it sends a request ID, local service identity, selected
   version and checksummed backup to the updater.
6. The updater reloads its root-owned local profile and the validated registry
   snapshot, obtains the repository location itself and queries releases again.
7. It selects an exact non-draft semantic version and binds manifest identity
   to that tag.

A checksummed last-known-good cache detects corruption and permits temporary
offline resolution. A checksum is not a signature; authenticity still depends
on the authenticated registry connection and protected local cache.

Channel policy MUST be explicit and uniform. Do not emit a manifest channel
that the installer ignores. Stable selection rejects prerelease suffixes at
both discovery and application boundaries.

## 28. Local Update-Helper Trust Boundary

One root-owned update-helper daemon serves a host. Multiple local applications share
its Unix socket but have separate registered profiles and control tokens.
Typed component operations for shared host agents are described in
[Service Agents: Deployment, Initialization And Lifecycle](./PART_09_SERVICE_AGENTS_DEPLOYMENT_AND_LIFECYCLE.md);
they do not widen this trust boundary into arbitrary command execution.

Required controls:

- Unix socket instead of a TCP listener;
- socket mode `0660`, dedicated group and explicit application membership;
- required local Host identity;
- one token per registered service, compared in constant time for mutations;
- exact match between requested service and registered profile;
- a host-wide mutation lock;
- rejection of a second daemon on an active socket;
- bounded bodies, downloads, headers and command durations;
- root-owned registry, job and backup paths with restrictive modes.

Read-only health and job status may rely on socket access. Update and rollback
require both socket access and the matching token.

The daemon needs root to control containers and rewrite root-owned deployment
files. Its system unit still constrains privilege with no-new-privileges,
private temporary storage, protected system/home paths, an explicit write-path
allow-list, restrictive umask and bounded journal rate. This contains
privilege; it does not eliminate it.

The runtime directory containing the Unix socket MUST be preserved across
update-helper restarts. On startup the daemon SHOULD detect a running registered
container whose bind-mounted socket directory no longer matches the host
directory and recreate only that affected service. It MUST leave healthy,
stopped and uncreated services untouched.

## 29. Update State Machine And Apply Algorithm

An update request is accepted only when a non-empty backup within the defined
limit matches its SHA-256. The implemented privileged boundary uses a 128 MiB
decoded-byte maximum. The backup is persisted before release resolution or
host mutation. Reusing the request ID returns the existing job instead of
starting a duplicate.

| State | Meaning |
| --- | --- |
| `REQUESTED` | Request, local identity and backup are accepted and persisted |
| `BACKUP_VERIFIED` | Backup bytes exist and match the supplied digest |
| `ARTIFACT_VERIFIED` | Tag, manifest, bundle, image and updater compatibility passed |
| `PULLING` | Exact immutable image is being downloaded |
| `APPLYING` | Version and image lock are written atomically and target is replaced |
| `HEALTH_CHECK` | Loopback and optional public endpoints are polled |
| `COMPLETED` | Installed version and digest are persisted in the job |
| `FAILED` | Failure occurred before rollback was possible |
| `ROLLING_BACK` | Previous version and optional logical data are being restored |
| `ROLLED_BACK` | Recovery completed and health passed |
| `ROLLBACK_FAILED` | Previous runtime or data could not be restored fully |

The updater applies a release as follows:

1. Resolve the exact release again and download the manifest and bundle over
   HTTPS with size limits.
2. Verify identity, version, bundle SHA-256, immutable image shape and minimum
   updater version.
3. Capture the currently running image and displayed version.
4. Pull the new image by digest before configuration changes.
5. Rewrite image and version together through a restrictive temporary file and
   atomic rename.
6. Replace only the target Compose service without removing persistent volumes
   or unrelated services.
7. Poll loopback health and, when required, public verified HTTPS health.
8. On failure after old state was captured, restore old image/version, start
   the old service, verify health and invoke its authenticated local restore
   endpoint with the backup.

Release resolution, compatibility or pull failure leaves the running service
untouched.

The reference updater verifies a newly downloaded Compose archive but reuses
the already installed Compose project rather than applying that archive. It
also validates that a database schema field exists but delegates migrations to
service startup. Consequently an image-only update cannot safely introduce
required Compose-structure changes unless the updater contract is extended.

## 30. Backup, Rollback And Job Retention

The application creates and imports logical backups. The updater treats them as
opaque bytes and verifies only safe filename, size and SHA-256.

A fresh backup may be staged for a short interval and downloaded by the
operator, or created immediately when the apply request starts. The unified UI
SHOULD make an operator-held copy explicit, especially before irreversible
schema changes.

Rollback restores image and version first, then sends the backup to the old
local restore endpoint. Both the updater call and restore endpoint use
constant-time token comparison.

Jobs are written through temporary files and atomic rename with mode `0600`;
backups live under mode-`0700` directories. Terminal job and backup retention is
bounded by both count and age. A practical baseline is the newest 20 terminal
jobs and 30 days.

Persisting a non-terminal job does not automatically resume its goroutine after
daemon restart. A new design MUST define startup reconciliation: resume safely,
roll back, or mark interrupted with an operator action. It must not leave a job
indefinitely ambiguous.

## 31. Update-Helper Self-Update

Self-update is an explicit privileged command. It resolves its own repository
from the same validated registry policy, selects an exact allowed version,
verifies a bounded manifest and binary SHA-256, and then:

1. copies the current executable to a previous-version path;
2. installs the staged executable atomically;
3. restarts the system service;
4. polls Unix-socket health for a short bounded interval;
5. deletes the previous binary only on success;
6. restores and restarts the previous binary on failure.

Binary self-update does not imply systemd-unit or package replacement. A change
to service hardening, runtime-directory behavior or packaging requires an
explicit signed package/install-repair contract and separate verification.

The selector MUST sort semantic versions and compare with the installed
version. Relying on the first provider API result is not a valid newest-version
algorithm. Every failed restart branch must attempt a restart after restoring
the previous executable.

## 32. Portable Client Update

A portable client receives a discovery URL, trusted public key, desired channel
and minimum allowed version from authenticated policy.

Before replacing itself it:

1. fetches the manifest over HTTPS without cache;
2. verifies schema, product role, required fields, channel, compatibility,
   artifact URL, size, SHA-256 and asymmetric signature over canonical JSON;
3. rejects downgrade and same-version/different-bytes cases;
4. downloads with a size limit and verifies artifact SHA-256 again;
5. stages through a temporary file and atomic rename;
6. launches a detached replacement helper and exits.

The helper preserves the current executable, starts the candidate with a
one-time health marker and waits a bounded interval. If the marker is not
created, it terminates the candidate, restores the previous executable and
starts it.

The controlling service performs the same signature, compatibility, size,
format and digest checks before caching client artifacts by digest. Network
failure or validation failure keeps the last-known-good or factory artifact.

## 33. Supply-Chain Guarantees And Boundaries

### 33.1 Guarantees Demonstrated By The Architecture

- server images install by immutable OCI digest;
- bundles, packages, binaries and backups are bound by SHA-256;
- off-host client manifests use asymmetric signatures;
- tag, version and manifest identity are cross-checked;
- privileged release paths accept HTTPS and allow-listed sources only;
- cross-repository assets are version-pinned and checksum-verified;
- build provenance is produced, and OCI builds request SBOM/provenance;
- runtime containers use least privilege and loopback-only publishing where
  possible;
- update success requires backup, health checks, persisted state and rollback.

### 33.2 Boundaries That Must Stay Visible

- A checksummed server manifest is not a signed manifest.
- Generated provenance is not enforcement unless installers verify it.
- Verifying that a tag exists is not cryptographic signed-tag verification.
- A version-addressed release may still be replaceable by repository
  administrators unless platform controls enforce immutability.
- CI actions referenced by moving major tags are not pinned to immutable
  commits.
- A dependency lock file is stronger than a bounded version range without
  package hashes.
- A public key downloaded beside an artifact is not a trust anchor and MUST NOT
  be used. First-install trust comes from the key embedded in the exact
  versioned service bootstrap; existing hosts use a transition signed by their
  already trusted key. No manual fingerprint step is part of release trust.
- A mutable `curl | sh` bootstrap is outside the protection of later artifact
  checksums.
- A locally smoke-tested build is not necessarily the exact published digest.
- Mocked updater tests are not an end-to-end container and system-service
  rollback test on a real host.
- Building a native package is not the same as installing and health-testing
  that package in CI.
- Unit-testing a replacement helper is not a complete end-to-end portable
  update and timeout rollback exercise.

Documentation MUST use precise words. Do not call a checksum a signature,
provenance generation provenance enforcement, tag presence signed-tag
verification, or a smoke test complete rollback validation.

## 34. Operator Update UI

The permanent Settings Updates section shows the installed version and separate
reachability for the local updater and approved release registry. The visual
contract is defined by Part 01 section 5.5 and its linked
`example settings updates` template.

`Check for updates` opens a custom overlay and performs discovery there. The
overlay shows:

- installed and available versions;
- repository policy source and last-known-good/offline status;
- local updater availability and busy state;
- selected tag, publication time and release notes;
- backup freshness, checksum and operator-copy status;
- job ID, exact machine state and message;
- rollback availability and final rollback result.

Release checking may be operator-triggered. Discovery can work without the
local updater, but installation is disabled with a clear explanation.

The overlay has two explicit phases:

1. **Discover and verify:** resolve only the approved source and verify release
   identity, signature/digest, compatibility and confirmation state. Show
   checking, up-to-date, offline/last-known-good and verification-failed as
   distinct outcomes.
2. **Initiate:** only when a newer confirmed release exists, show its verified
   details and an explicit update button in the same overlay. Discovery alone
   MUST NOT start installation, and the web client still cannot supply an
   arbitrary version source, URL, image or command to the updater.

The UI polls persisted job state. Temporary connection loss while the container
is replaced is not proof of failure. It MUST distinguish:

- rejection before mutation;
- new version failure followed by successful restoration;
- rollback failure requiring manual recovery.

`ROLLED_BACK` is not generic success, and `ROLLBACK_FAILED` is never hidden
behind the original update error.

Shared-agent checks use separately labeled component controls in the Backup,
messaging connection or central synchronization surfaces defined by the
[service-agent UI guide](./PART_10_SERVICE_AGENTS_UI_AND_OPERATOR_WORKFLOWS.md). Their
jobs use the same rule: request acceptance is pending, and the UI polls through
reconnect until a terminal state and refreshed component health are available.
