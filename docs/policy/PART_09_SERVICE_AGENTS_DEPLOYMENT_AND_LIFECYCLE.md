# Part 09. Service Agents: Deployment, Initialization And Lifecycle

This document is the Exocortex-wide source of truth for deploying, enrolling,
operating and updating the Linux service agents **Neptune** and **Gryphon** from
Kernel, Volt, Chronos and Saturn. It supplements the reusable deployment,
backup, update and security Parts with the concrete Exocortex topology.

This Part supersedes every former direct-connection compatibility note. Gryphon
is the single Telegram gateway: consuming services MUST NOT embed their own
Telegram polling or webhook runtime and MUST NOT store a bot token as an
application setting. Updater, Neptune and Gryphon ownership, trust and operator
flows are defined only in Parts 09 and 10.

This Part is subordinate only to the [Part 00 documentation authority](./PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md) and takes precedence over conflicting project-local documentation.

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT** and **MAY** are
normative.

## 1. Scope And Ownership

| Component | Host ownership | Primary responsibility | Consuming modules |
| --- | --- | --- | --- |
| Updater | One root-owned daemon per Linux host | Performs allow-listed privileged installation, enrollment and verified update jobs | Kernel, Volt, Chronos, Saturn, Neptune, Gryphon |
| Neptune Linux | One unprivileged `neptuned` daemon per Linux host | Exports module-owned recovery archives and optional dedicated mirrors to Saturn | Kernel, Volt, Chronos, Saturn; future approved modules |
| Gryphon Linux | One gateway service per deployment | Owns Telegram bot tokens, webhooks, update deduplication, callbacks and service-scoped bindings | Chronos and Saturn |
| Saturn | Central control plane and storage gateway | Issues one-time Neptune setup codes, owns desired schedules and remote commands, receives archives and mirrors | All Neptune deployments |

An application web process MUST NOT receive `sudo`, a Docker socket, the Gryphon
administrative socket or arbitrary command execution. UI actions call the
application backend; the backend calls the local Updater through its Unix socket
using the token for that registered service. Updater independently selects the
approved installer, repository, artifact and service profile.

## 2. Trust And Communication Topology

```text
browser
  -> authenticated module API
     -> /run/exocortex/updater.sock + per-head token
        -> allow-listed Neptune/Gryphon install, enroll or update job

module backup builder
  <- loopback/private export request from neptuned
neptuned
  -> Kernel Register (non-secret coordinates)
  -> Saturn HTTPS check-in, archive ingest and optional WebDAV mirror

Telegram
  -> public TLS webhook -> Gryphon
Gryphon
  -> authenticated Chronos/Saturn command adapter
Chronos/Saturn
  -> /run/gryphon/client.sock for status, linking and outbound notifications
```

The Updater socket is `/run/exocortex/updater.sock`. Each registered head has a
separate control token and exact service/profile match. Neptune uses
`/run/neptune/neptuned.sock` for local authenticated control. Gryphon exposes
`/run/gryphon/client.sock` to service containers and keeps
`/run/gryphon-admin/admin.sock` for root/local administration only.

Saturn never opens an inbound port on a Neptune host. `neptuned` polls Saturn
over outbound HTTPS, reports observed state and consumes monotonically revised
desired state and queued commands. A temporary Saturn outage does not erase the
last applied schedule.

## 3. Initial Deployment

### 3.1 Main modules and Updater

The normal module installer (`kernel-install`, `volt-install`,
`chronos-install` or `saturn-install`) installs or reuses the single host
Updater and registers its own head with a dedicated token. Initial deployment
MUST finish health verification before the UI offers privileged component
actions.

The active systemd unit MUST preserve the Updater runtime directory across
daemon restarts so existing container bind mounts continue to see the socket.
At startup the Updater also compares the host socket-directory identity with
the directory visible in each running registered container. When a stale bind
mount is detected, it recreates only the affected service container with its
existing Compose configuration. Healthy mounts are untouched; stopped or
uncreated containers are not started implicitly. An installation created by an
older unit may require one explicit container recreation before this protection
is active.

### 3.2 Neptune Linux

There is exactly one Neptune Linux daemon per host. It runs as a dedicated
unprivileged user. Its registry and durable journal live under
`/var/lib/neptune`; secret references and per-project credentials live under
`/etc/neptune` with restrictive ownership. Installation MUST verify the release
manifest and archive checksum and MUST NOT create a second daemon for another
module on the same host.

Neptune releases use `neptune-vMAJOR.MINOR.PATCH` and publish platform- and
architecture-specific archives and manifests for supported targets. The
installer selects the host architecture, verifies the manifest-declared bytes,
installs the native service and proves `/run/neptune/neptuned.sock` health.

Each module exposes an authenticated local export endpoint backed by the same
logical archive builder used by manual download and restore. Neptune treats the
archive as exact bytes: it does not unpack, rename, re-encrypt or recompress a
recovery ZIP.

The privileged CLI remains the installation, repair and emergency fallback:

```text
sudo kernel-install backup
sudo volt-install backup
sudo chronos-install backup
sudo saturn-install backup
```

If Neptune is absent, Settings MUST offer Initialize through the authenticated
local Updater. Updater installs a signed release, verifies health and enrolls the
requesting head. If a healthy instance already exists it is reused without a
download, restart or duplicate installation. A setup code is never persisted by
the web service. The operator sees a durable terminal job result.

### 3.3 Gryphon Linux

Gryphon is installed once and owns every Telegram bot token. Saturn Settings
provides typed installation and bot-registration actions through Updater. The
web process transiently forwards the operator-provided bot token and clears the
input; it never persists it or mounts the Gryphon admin socket. The equivalent
privileged recovery CLI remains:

```text
gryphon bot connect <bot-alias>
gryphon bot list
```

The connect operation reads the bot token without echoing it, verifies the bot
identity with Telegram, registers the webhook and stores a protected Gryphon
copy. Connected domain services never retain the bot token. Their installers
provision only `/etc/gryphon/clients/chronos.token` or
`/etc/gryphon/clients/saturn.token` and mount the service client socket.

Native releases use `gryphon-vMAJOR.MINOR.PATCH` with an
`exocortex.gryphon.release.v1` manifest. Initial installation extracts a
verified archive, runs `packaging/linux/install.sh` as root, configures
the protected Kernel bootstrap connection in `/etc/gryphon/gryphon.env` and starts
`gryphon.service`. The listener on port `18380` accepts only Telegram webhooks
and MUST be published behind HTTPS at that public origin. Persistent database
and protected secret copies under `GRYPHON_DATA_DIR` are operated and backed up
together.

## 4. Neptune Initialization

### 4.1 Operator workflow

1. In Saturn → **Synchronization**, create the required Linux pipeline identity
   and a single-use setup code. The code expires after 15 minutes.
2. On the target module host, open Settings → **Backup**.
3. When the panel reports `Detected · not linked`, select **Initialize
   Neptune**, paste the code and confirm.
4. The backend forwards only the setup code and its own registered service
   identity to Updater. The setup code MUST NOT be persisted by the module.
5. Updater validates the exact module profile, exchanges the code with Saturn,
   writes the scoped credentials, registers or repairs the project in Neptune
   and restarts only the required local service when necessary.
6. The UI polls the persisted initialization job through a service-authenticated
   status endpoint until a terminal state. A successful request is not a
   successful initialization.
7. After `COMPLETED`, the module reloads Neptune status and confirms the expected
   pipeline set. `FAILED` shows the sanitized terminal reason and a retry path.

The initialization state vocabulary is `REQUESTED`, `INSTALLING`, `ENROLLING`,
`COMPLETED` and `FAILED`. Temporary loss of the module API while its container
is recreated is an expected reconnect state, not an automatic failure.

### 4.2 Per-module profiles

| Module | Required Neptune registration | Successful postcondition |
| --- | --- | --- |
| Kernel | Recovery archive only, namespace `kernel` | Kernel archive project exists and is linked |
| Chronos | Recovery archive only, namespace `chronos` | Chronos archive project exists and is linked |
| Saturn | Recovery archive only, namespace `saturn` | Saturn archive project exists and is linked |
| Volt | Recovery archive plus dedicated `personal.volt` mirror | Both independent pipelines exist with the exact Volt profile |

Volt is deliberately not an archive-only special case. A single Volt setup code
provisions two credentials and two workers:

```text
recovery ZIP:  namespace=volt -> immutable Saturn backup archive
mirror:        mirrorRoot=volt, mode=single-file,
               targetFilename=personal.volt -> Saturn WebDAV /volt
```

The workers have independent schedules, states, retries and credentials and run
concurrently. The UI MUST wait for the Updater job to finish, reload Neptune
state and verify both rows. If one pipeline is absent or has the wrong profile,
Volt reports partial configuration and offers **Repair Neptune pipelines**;
it MUST NOT claim that backup is ready.

## 5. Ongoing Neptune Interaction

Saturn → **Synchronization** is the only authoritative operator control plane
for automatic schedules, explicit remote runs, identities, quotas, revocation,
fleet health and Neptune release commands. Module Settings exposes local status,
initialization/repair and navigation to Synchronization, but no second schedule
editor.

The archive and mirror paths remain separate:

- the module owns logical recovery format and restore semantics;
- Neptune spools exact archive bytes, records size and SHA-256, and uploads with
  a stable idempotency key;
- resumable upload continues from Saturn's accepted offset after restart;
- archive completion requires a Saturn receipt before spool deletion;
- disabling a schedule blocks new work but does not corrupt active work;
- a mirror compares content identity and updates only its dedicated root;
- producer credentials cannot write WebDAV mirrors, and mirror/device
  credentials cannot create recovery archives.

Recommended archive default is disabled with a 24-hour interval; the minimum
supported interval is one hour. Enabling a schedule sets the next run and does
not silently run it immediately. Volt mirror cadence is independent of its
recovery ZIP cadence.

## 6. Gryphon Initialization And Binding

Gryphon has three deliberately separate layers:

1. **Bot registration:** a privileged operator gives a Telegram bot token to
   Gryphon with `gryphon bot connect`; only Gryphon stores it.
2. **Service function connection:** Chronos or Saturn selects a ready Gryphon
   bot with **Link Chronos function** or **Link Saturn function**. The service
   receives only its scoped client credential.
3. **Telegram user binding:** after the function is connected, **Initialize
   bot** creates a service-scoped one-time `/link CODE` challenge. The operator
   sends it in a private chat with the selected bot. Linking one service does not
   authorize the same Telegram identity for another service.

The equivalent emergency CLI operations are:

```text
gryphon link issue chronos
gryphon link issue saturn
```

The UI MUST show the selected bot username, code expiry and a copy action. Codes
are single-use, short-lived and never accepted from group chats. Unlinking a
service function or Telegram user binding is explicit, audited and immediately
revokes the corresponding scope without deleting an otherwise shared bot.

Gryphon invokes only authenticated, allow-listed command adapters. Chronos and
Saturn do not poll Telegram, register webhooks or deduplicate Telegram updates.
Outbound reminders, summaries and responses go back through the service-scoped
Gryphon client socket.

## 7. Updates

### 7.1 Main applications

Kernel, Volt, Chronos and Saturn discover and apply their own releases through
the Updater contract in [Part 05](./PART_05_CI_RELEASES_AND_LOCAL_UPDATES.md). A
verified logical backup precedes application mutation; health checks and
rollback determine the terminal result.

### 7.2 Neptune and Gryphon

Component checks and installs use typed Updater component endpoints for
`neptune-linux` and `gryphon-linux`. Updater resolves the approved repository
from Kernel Register, selects an exact compatible release, verifies the
manifest and checksum, stages the artifact, performs the component-specific
atomic replacement, restarts the component and verifies its Unix-socket health.
The web client cannot supply a URL, executable path or command.

| Operation | Local Updater route |
| --- | --- |
| Initialize/repair Neptune profile | `POST /v1/components/neptune-linux/initialize` |
| Read Neptune initialization result | `GET /v1/components/neptune-linux/initializations/{id}` with the authenticated head identity |
| Check/update Neptune Linux | `POST /v1/components/neptune-linux/check` / `POST /v1/components/neptune-linux/update` |
| Check/update Gryphon Linux | `POST /v1/components/gryphon-linux/check` / `POST /v1/components/gryphon-linux/update` |

These are daemon-local routes. Browser-facing module endpoints proxy only the
fields required by their UI and never expose the Updater token.

Neptune fleet release policy and remote commands belong in Saturn
Synchronization. A local module panel may show the detected component version
and expose the approved check/install workflow, but it must not introduce a
second schedule authority. Gryphon version and update controls appear only in
Chronos and Saturn Bot connection panels.

Updater self-update is a separate binary lifecycle. Updating the executable
does not by itself replace arbitrary packaging or systemd definitions. Unit or
package changes require the installer/package repair path unless the signed
Updater release contract explicitly carries and applies them.

## 8. Failure, Recovery And Audit

- Every accepted initialization, repair, link, unlink, update and remote-run
  request produces a durable identifier and an audit event without secrets.
- UI success is based on a terminal job plus refreshed observed state, never on
  HTTP acceptance alone.
- A setup code, service token, producer token, bot token or `/link` code is
  never logged, returned in ordinary status, included in backup or stored in
  browser persistence.
- Timeouts preserve the job identifier and offer status reload; they do not
  encourage submitting duplicate jobs blindly.
- Retrying the same idempotent request returns or resumes the existing job.
- Revoked identities stop new work. Active archive/mirror operations terminate
  at a safe boundary and retain enough state for diagnosis.
- Manual CLI repair remains documented for an unavailable UI, absent agent,
  damaged packaging or an older deployment that predates the UI contract.

## 9. Required Evidence

An implementation is complete only when evidence covers:

- absent, detected/unlinked, initializing, linked, partial, failed, offline and
  update-available states;
- exact service/profile enforcement and cross-service setup-code rejection;
- final-state polling through the authenticated module proxy;
- module restart/reconnect during initialization;
- Volt archive and mirror workers running independently and concurrently;
- Saturn desired-state retention across temporary loss of connectivity;
- Gryphon bot registration, service linking and Telegram user binding as three
  separate authorization decisions;
- token redaction and inability of a service container to access Gryphon admin
  operations or another Updater/Neptune profile;
- verified component update, health failure and rollback/repair behavior.
