# Mastermind

[![Verify](https://github.com/psewdon1m-exocortex/mastermind/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/psewdon1m-exocortex/mastermind/actions/workflows/ci.yml)
[![Bridge package](https://github.com/psewdon1m-exocortex/mastermind/actions/workflows/bridge.yml/badge.svg?branch=main)](https://github.com/psewdon1m-exocortex/mastermind/actions/workflows/bridge.yml)

Source repository: [psewdon1m-exocortex/mastermind](https://github.com/psewdon1m-exocortex/mastermind).
The `Verify` workflow runs on pushes to `main`, pull requests and manual dispatch. Source
verification and protected release publication are separate gates.

The [standalone Mastermind Bridge](bridge/README.md) has its own tested download
packages and `bridge-v*` prereleases for manual installation in desktop Obsidian.

Mastermind keeps the canonical knowledge base as ordinary Markdown and assets in
an Obsidian Vault. The owned web interface provides search, activity, sharing,
Crusher intake/progress, settings and operations. The Vault tab embeds the pinned
native Obsidian runtime and retains Obsidian's own interface.

The production group has three containers: Core, Runtime and Crusher Worker.
Core coordinates every managed write and recovery boundary. The Worker has no
Vault mount or commit privilege. Kernel/Volt own shell secrets; community plugin
data inside `.obsidian` remains opaque. The central enrollment contract supports
archive, mirror or both, with the scoped Saturn reader accompanying mirror.
The host Updater handles the signed three-image update and rollback transaction.

The development version is **0.1.0**. Current acceptance evidence and remaining
gates are recorded in [IMPLEMENTATION](docs/IMPLEMENTATION.md). Development images
and local producer candidates are not published releases. See the exact
[producer patch lock](docs/compatibility.json) and
[final requirements](docs/requirements.md).

For local development, generate disposable credentials with
`python scripts/prepare_local.py` (root on Linux), build the Bridge with `npm ci && npm run build`
inside `bridge`, fetch the locked models with `python scripts/fetch_embedding_model.py`
and `python scripts/fetch_curator_model.py`, and use
`docker compose -f compose.development.yml up --build -d`. The development Compose
is a qualification fixture and uses loopback port 18390. Production uses
`compose.production.yaml`, an authenticated release bootstrap and
`mastermind-install`; host Nginx is configured separately by the operator.

Central `.docs` / [general](https://github.com/psewdon1m-exocortex/general) owns the
engineering rules. Mastermind links to it rather than retaining a policy copy.
[Governance](docs/governance.md) explains the immutable evidence reference and
[Conformance](docs/conformance.md) records remaining implementation gaps. Verification
can read the pinned catalog from a central Git checkout or fetch it with digest
verification; production runtime does not depend on a sibling source tree.

Use the [documentation index](docs/README.md) for product guides, operations and
development. Start with [Requirements](docs/requirements.md),
[Architecture](docs/architecture.md) or [Weaver](docs/WEAVER.md).
Earlier specifications and qualification ledgers are preserved in
[history](docs/history/README.md); they are not current deployment instructions.

Verification uses `python -m pytest`, `npm --prefix bridge test`,
`python scripts/validate_repository.py`, and the actual-host/browser probes in
`scripts`. Run `npm ci` at the repository root to install the pinned browser test
dependency. Linux-only checks run in the non-root, read-only Worker image;
Windows skips do not substitute for that run. `scripts/verify_producer_patches.py`
reconstructs all four producer candidates on their clean source baselines.
