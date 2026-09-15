# Part 11. Initial Multi-Service Deployment Profile

This profile implements the operator decisions through 2026-09-13 and takes precedence
over older CLI-only helper setup and device-only Volt unlock examples.
It is an explicitly product-scoped compatibility profile, not the generic
copy/paste installation template. The product-neutral happy path and placeholder
commands are defined in
[Part 04. Bootstrap And Deployment](./PART_04_BOOTSTRAP_AND_DEPLOYMENT.md).

This profile is governed by the [Part 00 documentation authority](./PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md) and takes precedence over conflicting project-local deployment documents for this topology.

## Scope and trust

Kernel, Volt and Saturn are main services. Updater and Neptune are per-host
singletons. Gryphon is installed for consuming services; in this profile Saturn
consumes it, Kernel and Volt do not. Head applications use authenticated typed
Updater operations. They receive no Docker socket, sudo or Gryphon admin socket.

The only discovery bootstrap exceptions are the protected Kernel origin and
service token on each host, and Kernel's protected Volt bootstrap origin/token.
Subsequent secret resolution and generated cross-service URLs use current Kernel
Register values. Kernel stores references, metadata and its local trust material;
it does not persist resolved domain secrets. Numeric Volt references are
`volt://UUID/1` through `volt://UUID/5`.

Volt unlock requires an Access Key. A protected key file is an explicitly supplied
Access Key; a device key alone is insufficient. A locked process remains reachable
for login and reports failed readiness until unlocked. ZIP v3 contains the
portable vault and logical records. Clean restore uses the archive's Access Key
and rewraps record keys for the target vault. The independent mirror is still
`/volt/personal.volt`; ZIP archives are under `/backups/volt` in Saturn storage.

Across every operator-facing service in this profile, an Access Key is an
explicitly supplied opaque exact value. No service may require a minimum or
maximum length, particular symbols or character classes, URL-safe/ASCII text,
an entropy score or a password/example denylist, and no path may trim or
normalize it. Missing configuration is invalid; the value itself has no
service-defined shape policy.

## First Register

`kernel/data/defaults/register.json` contains exactly 28 initial-profile keys,
including all six repositories and the Gryphon webhook origin. Empty references
are unconfigured state, not deployable values. Production coordinates and secret
values must never be invented by an installer. Store real values in Volt, then use
Kernel's profile API or `scripts/bootstrap-register.mjs` to import references and
run the semantic check. Pruning an older profile is explicit and its previous
Register revision remains restorable. The broader seed is preserved separately.

## Releases and host preparation

The current coordinated-deployment baseline requires Updater `0.4.3` or newer.
Every consuming repository MUST pin the exact tested Updater version in
`.release/updater.version`; release that exact `updater-vMAJOR.MINOR.PATCH`
artifact before publishing a consuming service bundle. A project pin may move
forward after compatibility verification but MUST NOT silently fall below the
profile minimum. The root installer
prepares fixed helper identities, directories, CLI links and systemd unit links
before starting Updater's restricted service. Healthy existing agents are reused.
Updater reconciles registered heads automatically: Kernel, Volt and Saturn require
Neptune, and Saturn also requires Gryphon. Missing helpers are installed once the
Kernel Register and host release trust are configured. On a completely empty
infrastructure these dependencies cannot be downloaded before Volt and the Register
exist; reconciliation retries automatically after they become available. It records
terminal installation jobs. Saturn enrollment and bot/user consent are completed
from Settings, independently of installing the daemon.
Gryphon release bundles include an architecture-specific Node runtime covered by
the artifact digest and manifest signature.

Kernel, Volt, Updater, Neptune and Gryphon manifests require RSA-PSS-SHA256,
3072-bit or stronger signing keys. The compatible Saturn Updater manifest uses
the same contract; Saturn's existing Ed25519 installer manifest is retained.
The detached envelope is `<manifest>.sig.json`. Every repository stores its own
private release-signing key in protected GitHub Secrets. Only its
service-qualified `service-vMAJOR.MINOR.PATCH` tag-triggered release signing job
receives that secret; the job signs the manifest, derives
the public counterpart and embeds only the public key in that service's
versioned `bootstrap.sh`. Windows Neptune ships its verifier public key in the
signed distribution.

On a clean host the service bootstrap atomically creates
`/etc/exocortex/release-trust/<service>.pem`; Saturn also creates
`/etc/vault/release-public-key.pem`. It verifies the signed manifest before
trusting any artifact URL or digest, downloads only that service and creates
only that service's configuration and `.env`. Each service therefore has an
independent bootstrap, trust file and environment file. Release trust uses no
`scp`, separately typed fingerprint or manually prepared public-key file.

`scripts/create-release-key.mjs` and `scripts/sign-release.mjs` provide initial
key generation and manifest signing. After the private key is enrolled in that
repository's protected GitHub Secrets, release CI owns signing and public-key
derivation; bootstrap owns host provisioning. Successful local tests do not
imply that a protected GitHub release job has signed or published the artifacts.

Saturn updates replace app/worker and web images together, migrate the database,
then verify health. Rollback restores the previous image pair and snapshot before
starting the older application. Updater self replacement runs in a supervised
process that survives restarting the daemon and verifies the resulting version.

## Public authenticated exposure

Browser owner/admin applications use the `public authenticated` profile. Their
canonical login pages are reachable from every client IP through the
server-managed Nginx. There is no `OPERATOR_CIDR`, operator VPN requirement or
source-IP allow-list. Before authentication they expose no operator data;
Access Key verification and bounded application sessions protect every data
route. `*_TRUSTED_PROXIES` identifies only the local Nginx hop and is not an
operator access list.

Kernel, Volt and Saturn bind application ports to loopback. One host-managed
Nginx owns public 80/443, TLS, WebSocket forwarding, limits and route policy.
No service bundles or starts Nginx or Caddy. Deny rules execute before proxy
handlers. The baseline has no coturn: ordinary browser and signaling traffic
uses Nginx. A real WebRTC NAT-traversal use case requires a separate explicit
TURN architecture decision because Nginx is not a TURN relay. Crawler
directives remain additional hints; they do not replace authentication.

Saturn public capability, authenticated backup/enrollment, WebDAV and Neptune
check-in paths remain available as required. Gryphon exposes only its authenticated
Telegram webhook path. Helper control APIs stay on Unix sockets or Windows pipes.

## Recovery and retained state

Kernel v3 preserves authoritative identifiers, revisions, histories and public
operator settings. Saturn recovery applies validated runtime public configuration
and storage profile settings with database rollback. External host credentials
must be provisioned before restore; incompatible storage access fails preflight.

The encrypted helper profile contains Neptune configuration, journal and spool,
Gryphon database, tokens, bindings and pepper, and Updater job/rollback history.
It excludes executable code, release trust keys, systemd units and main-service
deployment environments. Install trusted binaries and register target heads first.
Host-wide recovery is delegated only to a Saturn head explicitly granted
`UPDATER_HOST_RECOVERY_ALLOWED=true` by the host installer. Other heads cannot read
host-wide state or another head's jobs.

The helper archive uses AES-256-GCM with PBKDF2-SHA256 (600000 iterations), a random
salt and nonce, and a separately retained recovery passphrase. Limits are 128 MiB
of expanded data and 10000 files; an oversized export fails explicitly and never
silently omits state. Restore stages data, fsyncs a prepare journal, preserves old
directories until health verification, and recovers interrupted transactions on
restart. Running head containers reconnect to restored credential mounts. A new
Windows identity must re-enroll credentials protected by the previous machine's
DPAPI; its source folders remain operator-owned and must exist on the new device.

Saturn owns archive and mirror schedules independently. Remote commands expire
after seven days. Neptune/Gryphon retain bounded journal/deduplication history,
clear completed payloads and apply backpressure at capacity. A queued command or
accepted installation is not a successful terminal outcome.

## Deployment acceptance

Before publishing each service-qualified release, require the full
[Part 12 known-problem gate](./PART_12_KNOWN_DEPLOYMENT_AND_OPERATIONS_PROBLEMS.md)
and retain a `known-problems-report.json` bound to that service, exact service
revision, tag, immutable central-documentation revision and catalog digest. A
shared report cannot stand in for per-service scope.

Require checks for all seven documentation areas on each repository, plus the
connected real-service stand: authenticated Kernel→Volt, Linux recovery ZIP,
independent Volt mirror and Windows one-way folder synchronization, interruption
and retry, clean restore, private-edge negative tests, signed-artifact rejection,
and helper installation/reuse. Record actual PASS, FAIL and environment-limited
NOT_RUN separately. Local build/unit success alone is insufficient deployment
qualification.
