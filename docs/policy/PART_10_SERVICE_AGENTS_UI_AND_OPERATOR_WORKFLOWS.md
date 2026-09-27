# Part 10. Service Agents: UI And Operator Workflows

This document defines the Settings and control-plane UI for Neptune and Gryphon
inside Kernel, Volt, Chronos and Saturn. Component deployment and protocol rules
are in [Part 09](./PART_09_SERVICE_AGENTS_DEPLOYMENT_AND_LIFECYCLE.md); shared visual foundations are in
[Part 01](./PART_01_INTERFACE_AND_INTERACTION_UNIFICATION.md). This Part takes
precedence over conflicting project-local UI documentation.

The linked raster exports are composition references:

- [Backup panel](<./src/backup.png>)
- [Bot connection panel](<./src/bot connection.png>)
- [Updates panel](<./src/updates.png>)

Their true-black palette, square borders, typography, title hierarchy, row
geometry, spacing rhythm and full-width action placement are normative as
described below. Example names, versions and status values are placeholders.
Where an image contains an obsolete local schedule control or combines trust
decisions, this written document takes precedence.

## 1. Shared Panel Anatomy

Each panel is a full-width titled `4x` Settings card with the current persisted
ordinal, four-dot reorder handle, outer border and inset outline defined by Part
I. It uses the shared tokens:

- `#000000` page and control surfaces;
- `#FFFFFF` primary text and outer lines;
- 80%-white secondary text and inset lines;
- configured accent for focus, selected and intentional primary emphasis;
- `#62FF8C` success/ready and `#F83D3D` error/denied, always paired with text;
- Space Grotesk for page/service display names and Consolas for card titles,
  labels, values, actions and status text;
- square corners, no shadows and no gradients.

The desktop card keeps the reference `1610px` outer width at the `1919px`
viewport and derives all internal positions from card-local padding. The title
header is `55px` high. Content starts `27px` below the divider; named groups are
separated by `38–48px` according to the reference rhythm. Standard buttons and
status rows are `40px` high. Status rows expand horizontally but never compress
their label, terminal text or `18px` semantic square. Long versions and errors
wrap beneath the value rather than increasing every sibling row.

At narrow widths the card becomes one column; paired controls stack; buttons
become full-width; no horizontal scrollbar is introduced. Focus, hover,
disabled, pending and error states preserve geometry. Every action is reachable
by keyboard, every overlay traps and restores focus, and color is never the only
status signal.

## 2. Backup And Neptune Panel

The [Backup panel](<./src/backup.png>) supplies the visual grouping and alignment,
with a `1610x782px` source canvas,
but its project-local automatic schedule checkbox, interval and `Run backup now`
are legacy placeholders. Automatic schedules and explicit remote runs belong
only to Saturn → Synchronization.

Every module Backup card contains, in this order:

1. **System snapshot** — `Create and download snapshot` plus the module's
   inspect/restore action described by Parts 01 and 03.
2. **Automatic backup to Saturn** — explanatory text, local Neptune status and
   the one valid contextual action.
3. **Neptune version** when local component version controls are in scope —
   installed version, verified availability and an explicit check/install
   overlay or a link to the authoritative Saturn fleet control.

### 2.1 Status and action matrix

| Observed state | Required text | Primary action |
| --- | --- | --- |
| Neptune absent | `Not installed`; local Updater availability | `Initialize Neptune` through Updater |
| Installed, module missing | `Detected · not linked` | `Initialize Neptune` |
| Job accepted/running | Current state and stable job ID | Disabled pending action; automatic polling |
| Linked and complete | `Linked to Saturn` and last successful observation | `Open Synchronization` where useful |
| Volt has only one valid pipeline | `Partial configuration` and per-pipeline rows | `Repair Neptune pipelines` |
| Unreachable with cached state | `Offline · last seen …` | Retry/reload without discarding job ID |
| Terminal failure | Sanitized reason and failed state | Retry after correction |

`Initialize Neptune` opens a custom overlay with a single 32-character setup
code field, a concise instruction pointing to Saturn Synchronization, Cancel and
Initialize. The code uses `autocomplete="off"`, is never prefilled or persisted,
and is cleared after terminal completion or explicit cancellation. While the
job runs, the UI shows `INSTALLING`/`ENROLLING` progress and tolerates a bounded
API reconnect. It closes or converts to a final-result state only after the job
is terminal and status has been refreshed.

### 2.2 Module variants

| Module | Rows after successful initialization | Extra behavior |
| --- | --- | --- |
| Kernel | Local Neptune agent; recovery ZIP configuration | No Gryphon panel |
| Chronos | Local Neptune agent; recovery ZIP configuration | Has a separate Bot connection card |
| Saturn | Local Neptune agent; recovery ZIP configuration | Linked state directs to top-level Synchronization |
| Volt | Local Neptune agent; `Recovery ZIP`; `personal.volt mirror` | Both rows must be configured; partial state exposes Repair |

Volt's two pipeline rows remain separate even when both are healthy. They may
show independent enabled/disabled schedule summaries received from Saturn, but
they do not contain editable schedule controls in Volt Settings.

## 3. Saturn Synchronization

Saturn's top-level **Synchronization** page is not a duplicate Settings card.
It is the authoritative fleet control plane and separates:

1. Linux recovery archives;
2. Linux dedicated mirrors;
3. Windows folder synchronization;
4. identities, setup codes and revocation;
5. Neptune fleet version, heartbeat, observed/applied revision and commands.

Sensitive management starts with a fresh owner reauthentication. An identity
row shows namespace, deployment/server ID, role, quota use, last heartbeat,
desired versus applied schedule and last error. It provides explicit actions to
create a one-time setup code, edit archive and mirror schedules independently,
request an immediate run, request an approved agent update and revoke the
identity. An action reports a queued command first and later replaces that state
with the observed terminal outcome.

For Volt, the setup-code creator MUST label the combined profile **Volt ZIP +
personal.volt mirror**. Archive and mirror interval controls remain distinct in
the identity after enrollment.

## 4. Gryphon Connection

Saturn, Chronos and Mastermind render the `Gryphon Connection` card. It has one
`Gryphon bot binding` group with local-agent reachability, applied-connection
reachability, the selected bot alias or `none`, and one link/change action.
Registration, the one-time `/link CODE` pairing and shared version management
are performed in `sudo updater tui`.

### 4.1 Status and action matrix

| State | Required controls |
| --- | --- |
| Gryphon unavailable | Show unavailable reachability and keep function linking disabled |
| Gateway ready, no service connection | `Link Gryphon function` opens the paired-bot list |
| Service connected | `Change Gryphon function` opens the list with the active bot highlighted and non-secret details visible |
| Service binding unavailable | Show applied-connection reachability as unavailable; selecting the paired bot again may restore its verified account |

The selection overlay lists Gryphon-provided paired bot aliases and usernames
without exposing a bot token. Selecting one grants its verified Telegram
account access to this service without another `/link`. Its `Unlink all
adapters` action requires consequence text and removes only this service's
connection. Shared bots and other services remain connected.

## 5. Updates Panel

The [Updates panel](<./src/updates.png>) defines the alignment for application
version, Updater reachability, Register reachability and the full-width `Check
for updates` action. It represents the main-module release path only.
Its source canvas is `1610x566px`.

The permanent card contains:

- installed module version;
- local Updater availability;
- approved Kernel Register/repository-policy availability;
- `Check for updates`, which opens the discovery and installation overlay.

Discovery never installs. The overlay distinguishes checking, up to date,
verified update available, offline/last-known-good and verification failure. An
available release shows version, publication data, compatibility, backup
readiness and an explicit install confirmation. Once accepted, persisted job
state remains visible across the expected container reconnect and ends as
completed, failed, rolled back or rollback failed.

The Updater's own version row is not interchangeable with the module version.
Neptune version controls belong to Backup or Saturn Synchronization for
fleet-wide Neptune operations. Shared Gryphon version controls belong to the
Updater TUI. Each control names the component it will mutate.

## 6. Copy, Feedback And Error Recovery

- Use `Initialize Neptune`, `Repair Neptune pipelines`, `Link Gryphon function`,
  `Change Gryphon function`, `Check for updates` and `Install <component>
  <version>` consistently.
- Avoid `Connected` without naming what is connected: gateway, service
  function, Telegram user, archive pipeline and mirror pipeline are different
  states.
- Accepted asynchronous work uses informational/pending feedback. Only a
  terminal verified outcome uses success.
- Errors state what remained unchanged and provide the next safe action. Secret
  material, raw headers, filesystem credentials and unrestricted command output
  never appear.
- A disabled action has adjacent explanatory text; hover alone is not the
  explanation.
- Notices follow the shared Part 01 duration and stacking rules, while durable
  job progress remains inside the overlay or panel and is not communicated only
  by a transient toast.

## 7. UI Acceptance Matrix

Capture or test each applicable module at the standard desktop viewport and one
narrow viewport:

- Backup: absent, detected/unlinked, initializing, linked, offline and failed;
- Volt: both pipelines healthy, archive-only, mirror-only and wrong-profile;
- Gryphon: unavailable, ready/unlinked, function linked, challenge active, user
  bound and revoked;
- Updates: checking, current, available, applying/reconnecting, completed,
  rolled back and rollback failed;
- keyboard order, visible focus, focus trap/restore, reduced motion and status
  text independent of color;
- long versions, long bot usernames and sanitized multi-line failures without
  overlap, clipping or horizontal scroll;
- visual comparison against the three linked templates for palette, borders,
  typography, spacing, row height, action width and responsive composition.
