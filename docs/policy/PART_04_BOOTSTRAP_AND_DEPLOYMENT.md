# Part 04. Bootstrap And Deployment

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
## 18. Operator Experience: Prepare, Configure, Install

Initial deployment starts only after the operator has prepared the server, base
OS, network and required host access. It is intentionally a two-stage workflow
with one download command and one local install command for each service:

```text
1. Run one HTTPS bootstrap command.
2. Edit only the OPERATOR INPUT section of the generated .env file.
3. Run the installed service installer command.
```

A generic bootstrap invocation may look like:

```sh
curl -fsSL \
  https://github.com/OWNER/REPOSITORY/releases/download/service-v0.0.1/bootstrap.sh \
  | sudo sh
```

`OWNER`, `REPOSITORY` and `service` are placeholders; `0.0.1` demonstrates the
mandatory numeric version shape and the first releasable version. The real
command MUST name an immutable service-qualified release asset; it MUST NOT
fetch bootstrap from `main`, another mutable branch, a plain validation tag or
an unpinned "latest" URL. Later bundle checksum verification does not protect a
malicious mutable bootstrap script.

The first command prepares files; it does not pretend that unknown operator
inputs can be guessed safely. It ends by printing the exact `.env` location,
the section the operator may edit and the exact local command for installation.
Every deployable service publishes and owns its own `bootstrap.sh`; one
bootstrap MUST NOT silently prepare another application or merge multiple
services into a shared `.env`.

### 18.1 Standard Production Happy Path

Unless a service-specific constraint requires a documented variation, its
complete first-deployment procedure MUST remain this small:

```sh
# 1. Prepare this exact release; do not start the service yet.
curl -fsSL \
  https://github.com/OWNER/REPOSITORY/releases/download/service-v0.0.1/bootstrap.sh \
  | sudo sh

# 2. Edit only fields explicitly marked as operator input.
sudoedit /opt/exocortex/SERVICE/.env

# 3. Enforce secret-file permissions, install and verify locally.
sudo chmod 600 /opt/exocortex/SERVICE/.env
sudo SERVICE-install
sudo SERVICE-install status
curl -fsS http://127.0.0.1:LISTEN_PORT/HEALTH_PATH
```

Bootstrap MUST finish before the operator edits `.env`. At that boundary it has
already authenticated the release, pinned the embedded public release key,
verified the manifest, laid out the service files, written the immutable
release digest and generated every secret that does not require a human choice.
The generated `.env` clearly separates `OPERATOR INPUT` from generated secrets,
release locks and runtime defaults. The operator changes only the marked input
fields and does not manually recreate generated values or paste a release
digest.

`service-v0.0.1` is the canonical qualified-release example from Part 05. The
service slug is replaced with the current lowercase service identifier and the
numeric version with the exact intended release. A plain `v0.0.1` validation
tag never owns deployable artifacts and MUST NOT be used in a bootstrap URL.

The installer MUST NOT configure public ingress. Only after the local status
and loopback health checks succeed does the operator manually add or update the
service's virtual host in the existing server-managed Nginx, run `nginx -t`,
reload Nginx and test the canonical public HTTPS origin from an external client.
Service installation MUST NOT install, replace, start, reload or take ownership
of Nginx. A project-specific procedure MAY add required validation steps, but it
MUST preserve this ordering and explain every deviation.

## 19. Bootstrap Responsibilities

The root bootstrap MUST:

1. Refuse an unsupported operating system or architecture.
2. Install only the small prerequisite set needed for secure download,
   checksum verification and extraction.
3. Validate the public release key embedded in this service's versioned
   `bootstrap.sh` and install it atomically as
   `/etc/exocortex/release-trust/<service>.pem`.
4. If a service's own technical contract declares an additional legacy
   compatibility trust path, create it from the same embedded public key; no
   other service writes that path.
5. Bind the installation to the exact release identity carried by the
   versioned bootstrap. A `latest` discovery helper may select the release only
   before fetching bootstrap and must independently authenticate that mapping;
   bootstrap itself never silently changes to a newer version.
6. Download a narrow release manifest and its detached signature over HTTPS.
7. Verify the manifest signature with the locally installed public key before
   trusting any URL, digest, image or compatibility field.
8. Validate manifest schema, component role, exact tag/version binding,
   allow-listed artifact host, bundle digest and immutable image reference.
9. Download the service with retry, connection timeout and a size limit.
10. Verify the complete bundle SHA-256 before extraction.
11. Reject absolute paths and `..` traversal entries.
12. Extract without archived owner or permission metadata.
13. Install into a fixed root-owned directory.
14. Create only this service's namespaced configuration and mode-`0600` `.env`,
    then call the bundled installer in `prepare` mode.
15. Install a small administrative wrapper in the system path so later install,
    status and repair actions do not depend on the current working directory.

The bootstrap MUST NOT obtain a release public key through `scp`, download a
key beside the manifest, ask the operator to compare a release-key fingerprint
or require manual key-file preparation. The embedded key is the first-install
trust anchor. Therefore the bootstrap itself MUST come from the exact versioned
GitHub release or another immutable authenticated distribution path, never from
a mutable default-branch URL. An existing non-matching trust file is a key
rotation event and MUST NOT be overwritten merely by rerunning bootstrap.

The bootstrap SHOULD refuse to overwrite an already prepared installation.
Existing installations go through the updater or an explicit repair path.
Concrete installation and enrollment of shared host agents are defined in
[Service Agents: Deployment, Initialization And Lifecycle](./PART_09_SERVICE_AGENTS_DEPLOYMENT_AND_LIFECYCLE.md).

## 20. Environment File Contract

Each service has one separate generated `.env` file using mode `0600` and four
visually separated groups. It is never shared, sourced or rewritten by another
service:

| Group | Written by | Examples of content |
| --- | --- | --- |
| Operator input | Human | Public URL, one operator-chosen Access Key, certificate name, selected port, initial control-plane URL when required |
| Generated secrets | Prepare script | Session secret, database password, local update-control token and initial dependency credential reference when applicable |
| Release lock | Verified manifest | Semantic version and immutable image digest |
| Runtime defaults | Bundle | Listen address, timeouts and non-secret feature defaults |

Only the operator-input group is edited manually. Generated secrets use a
cryptographically secure random generator and are never printed. Machine-owned
values are rewritten through a mode-`0600` temporary file and atomic rename.

The product is single-operator and does not require an administrator username.
The initial Access Key is converted to the application verifier at bootstrap;
the login UI later accepts only that Access Key. An initial control-plane URL is a
first-start seed. After successful application initialization it is imported
into authenticated server-side settings, which become the authoritative value.
The runtime MUST define and expose this transition so `.env` and Settings cannot
silently compete as two sources of truth.

The Access Key is required only in the sense that the operator must explicitly
supply a value. Bootstrap and runtime MUST otherwise treat it as opaque exact
text. They MUST NOT impose an Access-Key-specific minimum or maximum length,
strength/entropy threshold, character-class or URL-safe/ASCII restriction,
breached/dictionary/example/placeholder denylist, trimming, normalization or
case folding. Templates SHOULD leave the field empty instead of inserting a
sentinel that could collide with a deliberately chosen literal value.

A control-plane access token is never stored as an ordinary readable setting. Initial
deployment injects it through the approved secret boundary or imports a secret
reference. Later rotation from authenticated Settings writes through a narrow
server-side secret operation; it does not give the web process permission to
rewrite arbitrary environment, deployment or release files.

Before start, validation MUST reject:

- unresolved structural placeholders or known example machine credentials in
  fields other than the Access Key;
- a missing Access Key, without applying any policy to a supplied value;
- a public endpoint that is not valid HTTPS;
- malformed or missing integration credentials;
- an out-of-range port or conflict with a protected host service;
- a missing certificate when TLS termination is local;
- an image that is not an allow-listed registry reference with a full SHA-256
  digest.

The application backup MUST NOT contain `.env`. Disaster recovery of deployment
secrets is a separate encrypted procedure.

## 21. Install Script Responsibilities

For a containerized service, the local installer:

1. Requires root only for host mutations.
2. Verifies the container engine, HTTPS client, cryptographic utility and
   Compose v2.
3. Validates operator input and release-lock values.
4. Pulls the exact image by digest before changing runtime state.
5. Installs or reuses one host updater and registers this local service with a
   separate control token.
6. Runs `docker compose config` as a fail-fast syntax and substitution check.
7. Starts the project detached.
8. Polls a loopback health endpoint with a bounded timeout.
9. On timeout, prints service status and only a bounded diagnostic tail.
10. Exits nonzero unless the service is healthy.

Installing a main module also registers its independent profile with the
privileged local update helper. It does not grant the application general root
execution. A shared host agent is
installed once and reused; later module enrollment adds only the module-scoped
profile and credentials.

The Compose production definition MUST rotate container logs, run application
containers as non-root where possible, drop capabilities, enable
no-new-privileges, use a read-only root filesystem where compatible and publish
application ports on loopback unless public exposure is explicitly required.

For a host-native daemon, the installer additionally verifies the exact OS and
architecture, checks system-service availability, copies configuration with
restricted owner/group, copies TLS material with restrictive modes, installs
the verified package, verifies any required host-management utility and its
protocol compatibility, enables the unit and checks HTTPS health. It SHOULD
NOT silently change the firewall; it reports the port that an operator may
choose to open.

### 21.1 Server ingress contract

Public HTTP(S), HTTP/2 and WebSocket ingress is owned by the server's single
host-managed Nginx instance. Application processes and containers publish only
their documented loopback upstreams. A service MUST NOT install, embed or run
an Nginx container, sidecar or second host daemon, and its lifecycle MUST NOT
own global `/etc/nginx/nginx.conf` state.

Each service supplies a versioned namespaced Nginx include or an equivalent
declarative upstream contract. Server configuration management owns its active
placement, domain, certificate paths and public ports, validates the complete
host configuration with `nginx -t`, and reloads only after the candidate
service is healthy. A failed validation or health check preserves the previous
include and routing. Service `.env` files configure loopback ports; they do not
become an alternate TLS or public-ingress authority.

The standard architecture does not deploy coturn. Browser requests, signaling,
long polling and WebSockets use Nginx. If a project genuinely requires WebRTC
media/data traversal across NAT, Nginx cannot perform the TURN relay role; that
project requires an explicit architecture and exposure review for a separately
managed TURN service. Absence of that concrete WebRTC requirement is `N/A`, not
permission to add coturn as a generic dependency.

## 22. Deployment Security And Limits

- The bundle checksum covers packages and bundled scripts; publisher identity
  comes from the signed manifest verified by the public key embedded in the
  versioned service bootstrap.
- An immutable image digest is the installed identity; a mutable tag is only a
  publishing convenience.
- Release values and generated secrets are never accepted from a web request
  during local installation.
- Archive extraction never preserves owner, group, setuid bits or arbitrary
  permissions.
- Health success is based on the running service, not on a successful process
  start command.
- Diagnostic failure output is bounded, for example to the most recent 100
  lines.
- A local loopback check that skips certificate-chain verification proves
  process reachability but not public TLS correctness. When public routing is
  part of the contract, run a second verified HTTPS check.
- Copying an integration token from a neighboring root-readable environment
  file is an implemented convenience pattern, but it increases coupling. A
  new design SHOULD prefer an explicit secret handoff or secret store.
- Root performs installation; the installed workload uses the least-privileged
  account available.

## 23. Deployment Verification

- [ ] The documented first step is one command and ends at a clear operator
      input boundary.
- [ ] Bootstrap identity is immutable or independently authenticated.
- [ ] The service has its own release `bootstrap.sh`, local trust file and
      mode-`0600` `.env`; none is shared with another service.
- [ ] Bootstrap installs its embedded public release key without `scp`, manual
      fingerprints or operator-prepared key files, then verifies the manifest
      signature before trusting release coordinates.
- [ ] Manifest version and component role match the selected tag exactly.
- [ ] Bundle bytes are checksum-verified before safe extraction.
- [ ] `.env` is created once with mode `0600`; placeholders cannot start.
- [ ] Internal secrets are generated automatically and never printed.
- [ ] The image is pulled by digest.
- [ ] Compose configuration is validated before start.
- [ ] A bounded loopback and, where required, public health check gates success.
- [ ] Re-running bootstrap cannot overwrite an existing deployment silently.
- [ ] Failure diagnostics and container logs are bounded.
- [ ] Host-native installation validates certificate, protected-port conflict,
      service state and health.
- [ ] Only server-managed Nginx owns public HTTP(S)/WebSocket ingress; the
      service has no embedded Nginx, and `nginx -t` gates an atomic routing
      change.
- [ ] coturn is absent unless a documented WebRTC NAT-traversal requirement and
      separate security decision explicitly make it applicable.
