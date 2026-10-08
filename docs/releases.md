# Releases and updates

The candidate numeric version is `0.1.0`; earlier `0.0.x` versions are unpublished local qualification fixtures. Branch pushes, a plain validation tag such as `v0.1.0`, and the protected deployable tag `mastermind-v0.1.0` are distinct workflows. Only the exact service-qualified tag may publish a deployable service release. Build service artifacts once, test them, sign those same bytes and promote the immutable digests.

## Standalone Bridge downloads

The separate [Bridge workflow](../.github/workflows/bridge.yml) builds and verifies
manual-install plugin packages on pull requests, `main` pushes and manual dispatch.
Only `bridge-v<version>` tag pushes publish a standalone Bridge prerelease. This
channel retains the shared Bridge/Core version, contains no service images or
bootstrap, and never promotes the service's stable/latest release. It does not
change the protected whole-service gates below. Package inventory, installation,
publication and retry instructions are in the [Bridge README](../bridge/README.md).

## Artifact contract

`scripts/build_release.py build` assembles a deterministic bundle from three already-built immutable image references, a full source SHA, the pinned public key and qualified Updater bootstrap files. `mastermind-release.json` binds service/version, platform, component images, Bridge/Obsidian/model, schema bounds, exact dependency tuple and individual bundle hashes. `bootstrap.sh` embeds the narrow verifier and public identity; it names an immutable version URL. RSA-PSS signing is a separate protected operation.

The release contains the Compose bundle, manifest and detached signature, bootstrap, public key and checksums, with SBOM/provenance, qualification results and known-problem evidence added by the release gate. Private release keys, `.env`, provider credentials, user Vaults and local integration fixtures never belong in a public artifact. Local qualification signers/registry/TLS fixtures are explicitly unpublished.

## Apply and automatic recovery

This is the required current workflow under central Parts 03 §13.2 and 05 §34.
The inspected source implements saved-copy protocol 2 but has a storage/limit
gap documented in [Conformance](conformance.md). Earlier disk-preimage and
24-hour-spool instructions are superseded.

1. Discover and select an exact compatible application version. Show its scope
   and recovery consequences before the operator's one confirmation.
2. Create a standard full encrypted recovery ZIP while holding the canonical
   writer barrier. Download that exact ZIP to the operator; do not substitute a
   settings-only export, a remote backup or a newly generated second snapshot.
3. Continue the same authorized update using the saved bytes and a receipt bound
   to the application, version, request, size and SHA-256. Do not require a second
   normal confirmation or file-picker round trip. Retain the original local ZIP.
4. Updater validates the exact topology and three-image compatibility group,
   executes migration and verifies native Bridge/Obsidian, Core and Worker health.
   Observe persisted job state; closing a browser does not cancel accepted work.
5. Uninterrupted failed updates may recover from the in-memory original ZIP.
   After helper restart or for later data rollback, request the original operator
   copy, verify its job-bound digest and explain that snapshot restore discards
   later edits. Distinguish rejection, verified rollback and rollback failure.

Archive bytes may live only in bounded memory or verified private tmpfs during
execution. Durable archive destinations are the operator computer and authorized
remote backup storage. The privileged update boundary defaults to 128 MiB decoded
ZIP; every participant must agree on a supported effective limit. Oversized full
backups block mutation rather than losing required contents. Ordinary reboot does
not require ZIP restoration. Retained metadata is not proof that backup bytes exist.

Core's current `mastermind.saved-copy.v2` integration requires matching Updater
capability and signed `saved_copy_protocol: 2` on compatible source/target releases.
A legacy source needs the explicitly qualified first-transition procedure from
Part 05 §35. Do not silently downgrade the protocol or use an undocumented old-image
restart command as migration. Later previous-version operations remain scoped to
the recorded own-head job and must state whether data is preserved or restored.

Shared Updater/Neptune/Gryphon/Wyvern install/check/update runs through
`sudo updater tui`, with exact version and shared impact confirmation. Those binary
operations do not use the application ZIP workflow. The installed service never
owns or uninstalls the shared agents.

## Gates

`python scripts/ci.py --images --secrets` executes the reproducible verification subset on a clean committed checkout. It validates the tag namespace, the pinned external policy digest, standalone links, pinned inputs, Python and Bridge checks; builds all three images; tests the code inside the exact Worker image under the production UID/read-only/capability limits; exercises the real offline model and extractor sandbox; and scans complete Git history plus an exported source tree. Results retain each command, exit code, duration, log hash and local image identity in `artifacts/ci/<revision>/result.json`. These component/image checks do not claim a host update or an eight-hour soak.

The verification workflow runs on pull requests, main pushes, plain `v*` tags and manual dispatch with read-only permissions and no signing secrets. Every third-party action is pinned in `.github/actions.lock.json`. Install the optional local hook with `git config core.hooksPath .githooks`. Set `MASTERMIND_PYTHON` if the interpreter is not named `python3`. Before a push, place the reviewed `mastermind.pre-push.v1` record for each outgoing commit in `artifacts/pre-push/<full-sha>.json`; `scripts/pre_push.py --record <record> --base <remote-sha> --revision <outgoing-sha>` validates the same record independently. A new remote branch uses forty zeroes as its base. Every record covers the complete changed-path list, all seven areas, inspected paths and hashed executed evidence from that revision. Security and private exposure cannot be marked N/A. Missing or stale evidence blocks the hook; the ordinary CI workflow repeats its machine-verifiable subset.

Before any push, review the complete outgoing diff for backup/recovery, update/rollback, embedded Documentation, technical docs/root README, security, public discovery applicability and private exposure. Every applicable area needs evidence. The Part 12 gate includes each active catalog ID exactly once, binds both source and catalog revisions, rejects stale/duplicate/omitted/UNKNOWN/FAIL records, and runs before signing-key access. Signature/asset checks finish before publication or discovery aliases move.

Tests include real host bootstrap, non-root permissions, malformed signatures/bundles, both independent Neptune pipelines, 350 MiB backup/restore/handoff, failed-update recovery, browser/capability boundaries and the bounded native Runtime regression. Per the [owner's acceptance decisions](acceptance-decisions.md), eight-hour endurance and actual 8 GiB payload transfer are excluded and remain explicitly not tested. Updater's bounded transport check sends 4 MiB and rejects oversized declarations before allocation. The current ledger records unfinished gates; this document describes the required release procedure and does not claim that an unpublished candidate is production released.

## Protected promotion workflow

`.github/workflows/release.yml` runs only for `mastermind-v*`. Its preflight job has read-only repository permissions and no signing secret. It consumes a previously completed qualification directory for the exact tagged SHA on a dedicated Linux runner labelled `mastermind-qualification`; set the repository variable `MASTERMIND_CANDIDATE_ROOT` to the parent directory. This runner must never accept pull-request jobs. Native and real-host qualification completes before the release tag is pushed; promotion verifies the original evidence and reuses the tested image group. The owner connected `https://github.com/psewdon1m-exocortex/mastermind.git` on 2026-09-16. Ordinary source pushes target `main` and trigger `Verify`; the protected release workflow has not run on GitHub. The owner explicitly authorized the complete source/CI migration and its necessary CI fixes as a scoped Part 07 decision, recorded in [acceptance decisions](acceptance-decisions.md). The dependency findings remain unresolved and continue to block release promotion.

The candidate directory contains `qualification.json`, `payload/` and the original hashed evidence. The payload has exactly the eight public assets declared in `scripts/release_candidate.py`: the unsigned manifest, Compose archive, pinned public key, bootstrap, three CycloneDX SBOMs and image provenance. A `mastermind.release-qualification.v1` record binds `revision`, `manifest_sha256`, all three registry `components`, local tested `image_ids`, an `assets` name-to-SHA256 map and `{path, sha256}` references named `ci`, `native_runtime`, `supply_chain`, `known_problems`, and `pre_push`. Its `checks` map must contain every profile check in that script, each referencing an executed `mastermind.verification.v1` record with exact source/manifest/components, command/exit status and hashes of its `raw_evidence`. Paths are relative to the candidate directory; links, escapes, stale bytes, incomplete native regressions and missing logs are rejected.

`provenance.json` uses `mastermind.image-provenance.v1` and binds `revision`, `manifest_sha256`, `components`, `image_ids`, and `ci_sha256`. The three public SBOMs must be the scanner's exact outputs. The ordinary scanner gate requires a complete successful fresh scan without unresolved High/Critical findings; changing its status string cannot bypass the severity checks. Unpublished producer patches and an effective central catalog absent from its pinned immutable commit also stop preflight. These are deliberate current blockers, not fabricated qualification results.

After preflight and an artifact secret scan, a fresh hosted job in the protected `mastermind-release-signing` environment receives only the public candidate. Configure `MASTERMIND_RELEASE_PRIVATE_KEY` there with the RSA identity matching the already-qualified public key. The private file exists only inside one temporary signing step; it is absent from job artifacts and subsequent step environments. The job creates GitHub provenance bound to this workflow/source/tag, signs the exact manifest and complete checksum inventory, verifies the archive's file inventory and generated bootstrap, and repeats the public-tree secret scan. All action revisions are pinned. Environment protection and immutable service-tag rules must be configured in the repository before enabling release publication.

The separate `mastermind-release-publication` environment has no release private key. It first creates a prerelease with `make_latest=false`, preserving the existing tag and refusing asset replacement. It downloads every required asset anonymously into a new temporary directory, repeats RSA-PSS/checksum/bootstrap/provenance checks, and pulls all three immutable images with an empty Docker client configuration. Only after the final Part 12 report passes does it attach the final evidence and mark the existing prerelease stable/latest. A failure leaves the candidate staged and does not move stable discovery. A retry can fill missing staging assets only when all existing bytes match; an already-final release cannot be overwritten or reinterpreted. This follows the central distinction between staging and final discovery. Actual production DNS, certificates and provider activation remain separate deployment checks.

Repository/environment settings and GitHub-hosted attestations cannot be exercised by local unit tests. The local tests cover real RSA signatures and archive verification plus adversarial evidence, identity, staging and failure controls; actual local bootstrap/update tests are recorded separately in the implementation ledger. No workflow, tag, key or artifact is published by running the local verification scripts.

## Weaver compatibility

The local candidate uses state schema 2 (migration input schema 1). Release
packaging binds `curator-model.lock.json` as well as the existing embedding lock.
The Worker embeds pinned Qwen3 GGUF weights, verified llama.cpp runner inventory
and their licenses. Preparation fetches these artifacts; runtime never downloads
an alternative. A previous schema-1-only Core cannot be run against schema-2 state.
See [Weaver](WEAVER.md#verification-record) for the newer evidence and remaining
stack qualification. The earlier context-indexing report is historical.

## Central evidence without a vendored policy tree

[Governance](governance.md) documents `docs/policy-lock.json` and offline central
checkout selection. Standalone verification can fetch the immutable catalog with
digest verification. CI still requires every active ID and exact candidate evidence;
removing copied Markdown never disables the gate. `publication_ready: false` remains
a blocker until current central changes and implementation gaps are qualified.
Release bundles include the active documentation and history under `docs/`, with
README as the only root Markdown document. They do not embed a second policy tree.
