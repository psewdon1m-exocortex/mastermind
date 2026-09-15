# Mastermind

Mastermind keeps the canonical knowledge base as ordinary Markdown and assets in
an Obsidian Vault. The owned web interface provides search, activity, sharing,
Crusher intake/progress, settings and operations. The Vault tab embeds the pinned
native Obsidian runtime and retains Obsidian's own interface.

The production group has three containers: Core, Runtime and Crusher Worker.
Core coordinates every managed write and recovery boundary. The Worker has no
Vault mount or commit privilege. Kernel/Volt own shell secrets; community plugin
data inside `.obsidian` remains opaque. One typed Neptune enrollment provides
independent full-backup and mirror pipelines plus scoped Saturn resource reads.
The host Updater handles the signed three-image update and rollback transaction.

The development version is **0.0.1**. Current acceptance evidence and remaining
gates are recorded in [IMPLEMENTATION](docs/IMPLEMENTATION.md). Development images
and local producer candidates are not published releases. See the exact
[producer patch lock](docs/compatibility.json) and
[final requirements](mastermind_service_requirements_final.md).

For local development, generate disposable credentials with
`python scripts/prepare_local.py` (root on Linux), build the Bridge with `npm ci && npm run build`
inside `bridge`, fetch the locked model with `python scripts/fetch_embedding_model.py`, and use
`docker compose -f compose.development.yml up --build -d`. The development Compose
is a qualification fixture and uses loopback port 18390. Production uses
`compose.production.yaml`, an authenticated release bootstrap and
`mastermind-install`; host Nginx is configured separately by the operator.

The effective central requirements are retained in [docs/policy](docs/policy/)
with a [content lock](docs/policy-lock.json). They remain usable after this service
is checked out independently. `scripts/export_integration_patches.py` exports the
necessary neighboring changes from disposable local clones; release and runtime
code do not read sibling checkouts.
