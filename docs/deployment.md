# Deployment

The production contract is Linux amd64, Docker Engine with Compose v2, three
pinned images, existing host Nginx and Kernel/Volt. Under central Part 13, the
installer ensures Updater, Neptune, Gryphon and default local Wyvern; scoped
enrollment and enabling service functions are separate steps. The development
fixture is not a production bootstrap. See [Compatibility](compatibility.md) for
producer qualification and [Conformance](conformance.md) for outstanding gaps.

## Prepare, configure, install

Use a service-qualified immutable release such as `mastermind-v0.0.1`. Obtain its `bootstrap.sh` and embedded public-key identity through the trusted release distribution channel. Execute that exact bootstrap as root. It verifies the RSA-PSS signature, role, version, component digests, dependency tuple and the bundle before preparing `/opt/exocortex/mastermind` and `/etc/exocortex/release-trust/mastermind.pem`. A plain validation tag never provides deployment assets.

Preparation starts no application and changes no ingress. It generates internal credentials, a private `.env` and `/usr/local/sbin/mastermind-install`. Edit only the marked OPERATOR INPUT section:

| Input | Meaning |
| --- | --- |
| `MASTERMIND_PUBLIC_URL` | Canonical HTTPS origin on port 443, with no path/query/credentials |
| `KERNEL_URL` | Existing Kernel HTTPS origin |
| `KERNEL_TOKEN_FILE` | Absolute root-owned mode 0600 file containing the exact machine token, without a trailing newline |
| `TRUST_CA_FILE` | Optional existing CA bundle; empty selects the system trust store |
| `MASTERMIND_TIMEZONE` | IANA timezone; defaults to UTC |

Then run `sudo mastermind-install install`. The installer validates immutable locks and file hashes, pulls the three exact linux/amd64 images, installs or reuses the declared host dependencies, registers only the Mastermind head and scoped clients and initializes only its owned volumes. It preserves other host agent registrations and never installs/reloads Nginx.

## Secrets and volumes

`secrets/core`, `secrets/runtime`, `secrets/worker` are root-owned directories with group 10001 traversal and explicitly enforced mode 0750, including under `umask 077`. Credential files are root:10001 mode 0640. Each container receives only its own read-only directory. Updater and Neptune UDS parent directories are mounted only in Core with their actual group IDs. No application container receives the Docker socket, host network, privileged mode or a writable root filesystem.

The installer owns `mastermind_core-data`, `mastermind_vault-data`, `mastermind_runtime-data`, `mastermind_work-data`; foreign volumes using those names cause refusal. The single application listener is `127.0.0.1:18390`. Runtime and Worker ports have no host mappings.

Runtime also joins its own `runtime-egress` bridge so Obsidian can resolve and
download community themes/plugins and use the owner's configured integrations.
Keeping it only on the internal `private` network prevents those native features
from loading. Development and production Compose both declare this egress;
it is separate from Worker egress and adds no published Runtime listener.

Before starting Core, provision the seven `services.mastermind.secrets.*` bindings listed in [security](security.md) through Volt references in Kernel. Generate recovery and signing identities independently of release/storage keys and retain their recovery escrow outside the Vault and backup ZIP.

For monthly Chronos reports, provision a dedicated opaque `chronos_report_token` in Volt and bind `services.mastermind.secrets.chronos_report_token` to it. Grant the Chronos Kernel machine principal resolution of that binding plus `services.mastermind.sni` and `services.mastermind.port`; Mastermind Core resolves the same token binding for request authentication. Keep this credential separate from the event-card reader token. In the Vault, create the branch note `chronos_analytics.md` and a template such as `root/templates/chronos_note.md` containing a literal `@chronos_analytics` link. Chronos selects that template in its Settings. Each accepted report is created as `Chronos YYYY-MM.md` in the Vault root.

## First native session and ingress

Inspect `installation.json`, `mastermind-install status` and `mastermind-install doctor`. A fresh Obsidian profile requires its native Vault trust confirmation. `OWNER_SETUP_REQUIRED` means the local containers and canonical storage passed their checks but Bridge readiness is still pending; it must never be called fully ready. The Shell exposes the native prompt in Vault. This explicit first-session step preserves native Obsidian ownership of plugin trust, including imported Vaults. It is the documented addition to Part 04's local-check ordering: proceed to ingress only after all other local checks and loopback health pass, then complete native consent and repeat doctor before accepting the deployment.

An operator renders `packaging/nginx/mastermind-server.conf.template` with the exact hostname and existing certificate paths. Include `mastermind-http.conf` once inside the existing `http` block. The template binds Host and TLS SNI, protects private paths, applies upload/rate limits and redacts capability paths. Run `nginx -t`, reload the existing host Nginx, then verify HTTPS from an independent client. Do not expose the raw Runtime, Worker or host agent sockets.

Sign in using the generated Access Key file, open Vault and confirm trust for the expected Vault. Enter a fresh 32-character Mastermind code from Saturn Synchronization in Settings → Backup → Initialize. The setup code declares archive, mirror or both capabilities. `COMPLETED` requires
all declared capabilities; mirror includes the authenticated resource reader.
Archive-only enrollment does not grant resource reads. Repeat doctor and observe
the selected schedules and remote receipts. Paired profiles retain one shared
enabled state and hourly interval. Enabling schedules does not request an immediate
manual remote run. See the selective-enrollment qualification gap in Conformance. Public DNS/certificate/external-vantage acceptance is an operator deployment check; a local test certificate does not certify a real public hostname.

## Repetition and failure

Bootstrap refuses an existing installation. After fixing operator inputs or a missing dependency, rerun the installed `mastermind-install install`; generated keys and authoritative volumes are retained. Inspect bounded error codes and the private installation report. Never repair by deleting volumes or replacing `.env` from a template. Use the own-head update workflow for version changes and [operations](operations.md) for data recovery.
