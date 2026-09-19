# Current acceptance decisions

The owner's explicit instructions on 2026-09-15 supersede the corresponding
Mastermind concept and acceptance requirements. General project Parts 00–12
remain authoritative for every unaffected requirement.

- Development and all active local verification use the main C: drive and its
  Docker Desktop engine. The external WSL migration has been abandoned.
- Do not run an eight-hour stability test. Native acceptance instead executes
  six real editor saves, two coordinated Core mutations, reconnects and one
  streamed representative Vault export. It verifies preserved text, no duplicate
  markers, durable delivery of native Activity to Core, image identity, no OOM
  and no container restart. The runner has a
  15-minute failure deadline, not a minimum waiting period.
- Do not transfer an 8 GiB payload for verification. The host Updater transport
  probe uses 4 MiB, including actual hashing/sealing, cancellation, authorization
  and expiry. An oversized declaration is rejected before payload allocation.
  Representative roughly 350 MiB backup, restore and pipeline checks remain.
- Runtime limits are unchanged. Long-duration stability and actual full-capacity
  8 GiB throughput are **not tested by owner decision**; neither is reported PASS.
- On 2026-09-16 the owner connected `origin` to
  `https://github.com/psewdon1m-exocortex/mastermind.git` and requested the first
  source push and verification CI. Earlier recorded test runs were local;
  the actual GitHub Actions result is recorded separately in the implementation
  ledger.
  Release publication and production deployment remain separate operations.
- The owner's subsequent explicit instruction to migrate the complete local
  repository and pipeline to GitHub authorizes the initial `main` history push
  and the follow-up commits needed to make hosted `Verify` pass. This is a scoped
  source/CI migration decision under Part 00/Part 07 despite the already reported
  image dependency findings. It does not turn the failed security assessment
  into a passing scan or authorize release tags, image publication or deployment.
  The normal security and qualification gates remain required for promotion.
- On 2026-09-19 the owner revised the Shell: remove the Analytics destination
  and Dashboard Service status card; put Connectedness and Total items in 2x
  Dashboard cards, Activity Heatmap in 4x and Crusher access in 1x. Remove the
  Vault portable-download button, use lowercase page headings, retain sidebar
  label capitalization and use the supplied brain logos. Part 01 remains the
  authority for hover bounds, search controls and the Documentation workspace.
  Existing saved orders retain surviving items and append new cards; no stored
  Vault or backup schema changes are required.
- On 2026-09-19 the owner further requested a single-line sidebar wordmark,
  a 90-degree browser icon rotation, hover on every Dashboard card, and the
  supplied untitled action-card layout for Crusher access. The sidebar name
  uses a bounded 36px size to fit the existing 250px sidebar. The icon is the
  supplied image; the subsequent Shared/UI follow-up replaces the initial SVG with browser-sized PNGs and rotates the displayed tab icon a further 90 degrees.
  The explicit Create & copy action is the owner's one-gesture clipboard
  variant: initiate the write from that trusted action with promise-backed
  generated data, show Copied only after success, retain a selectable value
  and a fresh Copy action when the browser declines. Six-digit codes and their
  existing one-use/30-minute contract are unchanged. This replaces the modal.
  Obsidian Runtime receives its own outbound network for native catalogs and
  plugin integrations; its ports remain unpublished and its credentials scoped.

- The subsequent 2026-09-19 follow-up renames the owner destination to Shared
  while retaining legacy bookmarks and saved navigation order. Revoked links
  disappear from the owner list; internal revocation records remain authoritative.
  The supplied Shared reference becomes expandable note rows with real metadata;
  its file-download counter is replaced by the note access status. Sidebar
  ordinals remain visible next to, rather than behind, reorder handles. Search
  and notification geometry follow current root Part 01. Local Crusher fixture
  success is explicitly distinguished from live Google API readiness.

The final three-image build, 510-test Linux suite, bounded native and producer
regressions, clean host installation and update/rollback recovery have passed
locally. Remaining release work covers dependency remediation/review, immutable
upstream producer/policy identities and protected publication setup in the newly
connected repository. Physical removal of the stopped external copy and unused C: transfer
credentials was rejected by automatic execution review. See the current
[implementation ledger](IMPLEMENTATION.md) for evidence and exact limitations.

The changes above need no data migration and do not change backup compatibility.
Rollback continues to use the encrypted pre-update snapshot and tested group
rollback. Reinstating excluded endurance tests requires a new owner decision.

## Public Crusher and direct Shared editing — 2026-09-19 follow-up

The owner's subsequent twelve-point request supersedes the earlier sidebar
handle, hash-only copy and password-length decisions:

- Remove navigation dot handles and the visible collapsed-menu arrow. Preserve
  numbers, row drag and keyboard ordering. Rotate the currently displayed tab
  artwork another 180 degrees, retaining the three native PNG sizes.
- Public Crusher has a centered code gate, then a link/file-drop interface with
  a fullscreen drag overlay and inherited Mastermind accent. No source-type
  selector is shown. Existing source APIs and progress-only permissions remain.
- Create share is an explicit create-and-copy gesture and closes its overlay.
  Clipboard denial retains manual copy and retry. The owner's instruction
  selects this gesture instead of the generic two-step clipboard pattern.
- Copy link remains available after reload. A signed deterministic URL is
  recoverable from the existing record ID and private Share pepper; older raw
  URLs remain valid aliases. There is no plaintext-token storage or DB migration.
  Old binaries do not recognize the new v2 URL format, so rollback compatibility
  must include the URLs as well as schema and backup state.
- Shared passwords have no minimum or complexity rules; `1` is accepted. Empty
  means no password. Request bounds, Argon2 and rate limits remain.
- Shared opens directly as title plus note, with inline Markdown editing when
  granted. Autosave uses a checked version after native dirty-buffer flush.
  Conflicts retain the draft and require explicit merge; they never silently
  overwrite another writer. See [Sharing](sharing.md) for the exact contract.

The next layout follow-up removes the visible Submissions heading and uses
history/search on the left and source input/drop on the right, shrinking both
columns when the sidebar is fixed. Narrow content widths stack the panels.
Visual scrollbars are suppressed on all Mastermind Shell/public pages while
wheel, touch and keyboard scrolling remain available; the existing native
Obsidian UI exception remains in force.

## 2026-09-19 — Native Obsidian graph and link panes

The owner requested implementing and testing `@note`, Chronos and Saturn in native Obsidian graphs, then removing redundant custom graph structures if successful. Graph view, Local graph, Backlinks and Outgoing links now use the native views with an ephemeral reference adapter. The three separate Mastermind panes/commands, custom canvas renderer, portable graph cache and unused Bridge graph endpoints are removed. External resources remain virtual targets, subject to the native Existing files only filter. No proxy notes or Markdown rewrites are introduced. Native qualification is limited to the pinned Obsidian 1.13.7; live external card transport remains the existing managed integration.
