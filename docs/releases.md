# Releases and updates

The initial numeric version is `0.0.1`. Branch pushes, a plain validation tag such as `v0.0.1`, and the protected deployable tag `mastermind-v0.0.1` are distinct workflows. Only the exact service-qualified tag may publish a release. Build artifacts once, test them, sign those same bytes and promote the immutable digests.

## Artifact contract

`scripts/build_release.py build` assembles a deterministic bundle from three already-built immutable image references, a full source SHA, the pinned public key and qualified Updater bootstrap files. `mastermind-release.json` binds service/version, platform, component images, Bridge/Obsidian/model, schema bounds, exact dependency tuple and individual bundle hashes. `bootstrap.sh` embeds the narrow verifier and public identity; it names an immutable version URL. RSA-PSS signing is a separate protected operation.

The release contains the Compose bundle, manifest and detached signature, bootstrap, public key and checksums, with SBOM/provenance, qualification results and known-problem evidence added by the release gate. Private release keys, `.env`, provider credentials, user Vaults and local integration fixtures never belong in a public artifact. Local qualification signers/registry/TLS fixtures are explicitly unpublished.

## Apply and automatic recovery

Core asks its authenticated Updater head to resolve the approved repository independently and pre-pull all three candidate images before retaining the snapshot barrier. It creates a consistent encrypted preimage and streams it to a head/request-bound spool, which Updater verifies and seals. Apply retries preserve durable identity.

Updater validates both installed and candidate topology, pinned images, source/target mounts, UID, capabilities and loopback listener. It stops only Core, Runtime and Worker, changes the versioned deployment files and release metadata, runs the typed offline migration, starts the group and checks schema, canonical Vault, actual Bridge/Obsidian and Worker/model. Core resumes owner writes only after observing a verified terminal result.

A failed migration or functional check restores the prior deployment files, image group and pre-update data before starting the old application. A process interruption retains a recovery job and blocks unsafe new work. `ROLLBACK_FAILED` is a distinct state requiring operator recovery. A completed update cannot be rolled back by calling the legacy endpoint without a fresh Core barrier; it would otherwise discard subsequent native edits without a verified current snapshot.

Settings → Updates → Return to previous version starts a new transaction. Updater accepts only the exact previous manifest and component digests recorded by a completed update of the currently installed own head. Core creates a fresh encrypted snapshot and retains its barrier. A compatible previous release opens the current data; it does not rewind notes to the earlier update date. Incompatible schemas reject the change and recover the current version/data. CLI equivalents are `mastermind update previous` and `mastermind update rollback --job <id> --yes`.

Application Apply also updates its own verified copies in `vendor/updater` so that a later explicit installation/repair can verify the complete signed inventory. Apply never executes those copies or changes the installed host agent/trust. Terminal Core preimages and sealed host spools expire after 24 hours; uncertain or failed recovery retains its data and excludes new host mutations.

## Gates

`python scripts/ci.py --images --secrets` executes the reproducible verification subset on a clean committed checkout. It validates the tag namespace, policy inventory, standalone links, pinned inputs, Python and Bridge checks; builds all three images; tests the code inside the exact Worker image under the production UID/read-only/capability limits; exercises the real offline model and extractor sandbox; and scans complete Git history plus an exported source tree. Results retain each command, exit code, duration, log hash and local image identity in `artifacts/ci/<revision>/result.json`. These component/image checks do not claim a host update or an eight-hour soak.

The verification workflow runs on pull requests, main pushes and plain `v*` tags with read-only permissions and no signing secrets. Every third-party action is pinned in `.github/actions.lock.json`. Install the optional local hook with `git config core.hooksPath .githooks`. Set `MASTERMIND_PYTHON` if the interpreter is not named `python3`. Before a push, place the reviewed `mastermind.pre-push.v1` record for each outgoing commit in `artifacts/pre-push/<full-sha>.json`; `scripts/pre_push.py --record <record> --base <remote-sha> --revision <outgoing-sha>` validates the same record independently. A new remote branch uses forty zeroes as its base. Every record covers the complete changed-path list, all seven areas, inspected paths and hashed executed evidence from that revision. Security and private exposure cannot be marked N/A. Missing or stale evidence blocks the hook; the ordinary CI workflow repeats its machine-verifiable subset.

Before any push, review the complete outgoing diff for backup/recovery, update/rollback, embedded Documentation, technical docs/root README, security, public discovery applicability and private exposure. Every applicable area needs evidence. The Part 12 gate includes each active catalog ID exactly once, binds both source and catalog revisions, rejects stale/duplicate/omitted/UNKNOWN/FAIL records, and runs before signing-key access. Signature/asset checks finish before publication or discovery aliases move.

Tests include real host bootstrap, non-root permissions, malformed signatures/bundles, both independent Neptune pipelines, 350 MiB backup/restore/handoff, failed-update recovery, browser/capability boundaries and a full eight-hour native Runtime run. Short or interrupted soaks cannot become PASS. The current ledger records unfinished gates; this document describes the required release procedure and does not claim that an unpublished candidate is production released.
