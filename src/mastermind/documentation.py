"""Versioned, authenticated operator articles shipped with the implementation."""
from markdown_it import MarkdownIt

ARTICLES = [
    ("introduction", "Introduction", """Mastermind keeps a canonical Obsidian Vault and the service state needed to operate it.
The owner uses Dashboard, Vault, Crusher, Analytics, Shares and Settings. Documentation and Logout remain in the bottom navigation group.

### Your first session
Sign in with the exact Access Key. Spaces, Unicode and line breaks are significant. Paste preserves the exact clipboard value; Shift+Enter adds a line break. Enter submits. An empty Access Key is valid only if it was explicitly configured.
An owner browser session lasts 12 hours. Ten owner sessions can coexist; Vault connects them to the same graphical Obsidian instance. Logging out closes that browser's Runtime connections. Access Key rotation ends the other sessions.

### Dashboard
CPU and RAM describe the server visible to the service. Disk describes the filesystem holding the canonical Vault, using space available to the service account. Uptime starts with the current Core process. Unknown or unavailable data are labeled explicitly.
Drag a card or navigation handle to reorder it. With the handle focused, Alt+Arrow Up or Down performs the same change. Orders are saved on the server.
"""),
    ("vault", "Vault and references", """Vault opens the genuine Obsidian application through the authenticated Runtime gateway. Its themes, typography, dialogs and keyboard shortcuts follow Obsidian. Shell appearance does not rewrite Obsidian settings.

### Editing and navigation
Use the native editor, quick switcher and file manager. Mastermind Bridge adds internal `@note` references, autocomplete, reading and hover views, outgoing links, backlinks and a graph alongside native wikilinks. Markdown code, frontmatter and excluded HTML are not interpreted as references.
Use **Create note through Mastermind** and **Delete current note through Mastermind** in the native command palette for coordinated creation and deletion. Note basenames are unique across folders after Unicode normalization and case folding.
Native file-manager rename updates native links. Mastermind coordinates the operation and updates its own references. Folder moves preserve note names, attachments, empty subfolders and Share paths.

### External resources
Chronos references show the minimal permitted event card. Saturn resources are read through the local Neptune agent with owner authorization. A native Download command prepares an explicit download in the Vault toolbar. Shared visitors have no access to either resolver.

### Reconnect and portable copies
Reconnect attaches to the existing graphical session. Fullscreen expands the Vault viewport; Exit fullscreen returns to the Shell. The graphical stream does not expose the native document as a web screen-reader tree.
Download Vault copy produces a normal ZIP with the complete Vault and its original Obsidian plugin data, which may contain plugin credentials. The included Bridge supports local references and graph features in a standalone Obsidian copy. External service references show unavailable there. Editing that copy does not synchronize it back.
"""),
    ("crusher", "Crusher submissions", """Choose text, a web page, file, YouTube video, Git repository or an owner-selected Saturn file. Submit one source and follow its confirmed processing stages. The page shows source identity, progress, stage and a sanitized failure message. The resulting note is found in Vault.

### Owner and visitor access
The owner can create a six-digit one-time code valid for 30 minutes. A visitor activates it at `/crusher` and receives a 30-minute submission session. Receipts permit checking accepted jobs for 24 hours while they remain in the tab. The visitor cannot browse Vault or select private Saturn resources. Reloading the visitor page discards its in-memory session and receipts.

### Limits and placement
Text input is limited to 1 MiB and uploaded sources to 2 GiB. Uploads are hashed incrementally in a browser worker and checked by Core. Public URL fetching is restricted to validated public addresses; private network targets and arbitrary Git helpers are rejected.
One pipeline runs at a time. Each job has a 60-minute deadline and at most three attempts per retryable stage. The local multilingual model indexes Vault text without sending it to an embedding provider. Placement uses a bounded hierarchy of root, main and nested key notes. Only selected, bounded context reaches the configured AI provider. Ambiguous placement uses Inbox.
An interrupted operation resumes from durable checkpoints. Failed or unavailable source material must be resubmitted; a successful result is committed once. The provider key and approved models must resolve through Kernel and Volt.
"""),
    ("analytics", "Analytics and Activity", """Analytics shows the Activity Heatmap, note count, distinct internal edges, broken internal references and Connectedness.

### Activity events
Only owner CREATE, EDIT, RENAME and MOVE actions count. Autosaves belong to one edit session. It closes when focus changes to another note, the note closes or 300 seconds pass after the last edit. A simultaneous rename and move contributes both events. Reading, navigation, indexing, public edits and automated Crusher writes do not count.
Events remain in UTC. Settings → Appearance → Activity timezone changes calendar grouping without rewriting history. Select up to 731 days. Day intensity is the count divided by the largest displayed count, with four nonzero levels. A single action on the only active day receives the brightest level.

### Connectedness
Native and Mastermind internal references form one undirected graph. Duplicate and self links do not increase its edges. For N notes and E distinct edges, Connectedness is `100 × 2E / (N × (N − 1))`; it is zero for fewer than two notes. External service links do not enter this percentage.
"""),
    ("shares", "Shares and public editing", """A Share is a capability URL for one current note, with view or edit permission, optional password and optional expiry. It grants no directory, search, neighbor, attachment, graph or external-resource access.

### Create and copy
Select Create Share, provide a note path and policy, then keep the returned URL. Copy works only on an explicit click; a selectable complete value is always available if clipboard access fails. The raw URL stays in this owner's browser memory. Reload or a new login cannot recover it from the server's hash. Create a new Share if it is lost, and revoke the old one separately.
Passwords contain 12–128 characters, at most 256 UTF-8 bytes, with no line breaks. Expiry can be up to 365 days ahead. Policy changes invalidate existing visitor sessions. Revoke permanently disables that capability.

### Public projection
Visitors receive an isolated note projection. Links, references, frontmatter and protected content remain outside editable fields. The server rejects reference syntax and encoded bypasses before reconstructing Markdown. Concurrent modifications cause a conflict and preserve the visitor's safe draft for review.
An active Share to a missing note reports that its target is gone. Creating a different note at the same path makes that path-bound Share live again. Native rename and folder moves update the tracked Share paths.
"""),
    ("settings", "Appearance and Security", """Appearance changes belong to the server. Accent changes preview immediately; Apply validates contrast and persists them. Reset previews the default blue; Apply is still required. Other ordinary settings commit immediately and revert visibly on failure.

### Changing Access Key
Provide the current exact value and two matching new values. Fields start empty and are never filled from stored credentials. The new verifier is committed atomically; other sessions end. The current browser receives a replacement session.

### Kernel connection
Change the Kernel URL or replace its token in separate actions. A real Register and Volt resolution verifies the proposed connection before activation. Invalid credentials, TLS, transport or schema failures leave the old connection active. Only the committed server URL is authoritative after reload.
Token replacement is write-only and ends browser sessions. The bootstrap credential lives outside Vault and normal backup state. Provider, backup and Share secrets belong to Volt through Kernel. Obsidian plugin data are not inspected or migrated by these settings.
"""),
    ("backup", "Backup and Restore", """Create and download snapshot prepares a fresh encrypted logical ZIP, then starts its browser download while Settings stays open. It contains the full Vault, Activity, reference history, Share policy and revocations, mandatory Crusher records and non-secret settings. Active sessions, temporary sources and derived indexes are excluded.
The payload uses age/X25519 encryption and an independently trusted Ed25519 signature. Keep the recovery identity, trust key, relevant Share pepper versions and bootstrap credentials outside the encrypted archive. A backup cannot recover its own missing decryption key.

### Inspect and restore
Select a recovery ZIP of at most 8 GiB. The server checks signature, ciphertext, bounded unpacking, inventory hashes and logical state before showing its date, size, schema and note count. Restore requires explicit confirmation and creates a pre-restore safety backup. Current Vault and mandatory state are replaced as a coordinated generation switch; a verified copy is booted before commit. Active sessions end. Sign in again and inspect the operation outcome in Settings.
Expanded archives are limited to 32 GiB and 100,000 entries. Recovery uses a 96 GiB bounded spool and requires sufficient filesystem space. Completed and abandoned owner staging expires after 24 hours; Remove deletes an idle staged operation sooner. Active transfers and running operations cannot be removed.
Known newer local Share revocations are retained during restore. A disaster restore without that newer revocation state returns Share policies to the snapshot; review restored Shares.

### Independent remote pipelines
Neptune archive and mirror have independent schedules, credentials, generations and last successes. Schedules belong to Saturn Synchronization. Mirror is a complete private Vault tree; it is not a replacement for encrypted full recovery. Initialize / Repair uses a fresh typed Mastermind enrollment code. Missing agents, unreachable sockets, enrollment and authenticated readiness are different states.
"""),
    ("updates", "Updates and recovery", """The local Updater owns installation. A Mastermind release binds Core, Runtime and Worker image digests to compatible Bridge, Obsidian, schema and model artifacts. Check for updates verifies the approved release source. Discovery alone never applies a release.
Apply is available only after compatibility is confirmed. Preparation occurs before the write barrier; the service then seals a recovery snapshot and hands it to the local helper. The helper stops and updates the component group, performs migration and functional checks, and resumes the service only after successful verification.
Failure restores the previous data and all previous images before older code can open newer schema. An unknown writer or incomplete rollback keeps the service unavailable with retained recovery evidence. Do not delete the recovery journal or manually mix image versions. Use the exact release's operator runbook to diagnose and recover.
Shared-agent and helper self-updates have separate control-plane workflows. The main-module Apply button does not update unrelated components.
"""),
    ("logs", "Logs and troubleshooting", """Settings → Logs displays a bounded stream with type, body and local time. The browser retains at most 200 rows and pauses polling while hidden. Download archived logs produces a ZIP without leaving Settings.
Operational audit retains at most 10,000 events, 30 days and 64 MiB. JSONL rotation uses 5 MiB files and a 64 MiB directory limit. Activity is separate domain history and is not purged with diagnostic logs. Recursive redaction removes credentials, sensitive URLs and full content before sinks.

### Common recovery actions
If Runtime is recovering, keep the page open or use Reconnect. If a source fails, review its sanitized error and correct the source or configured dependency before resubmitting. Kernel failure requires checking its TLS, service credential and Volt bindings. Neptune and Updater require their actual local sockets and scoped credentials.
NOT_READY or RECOVERY_REQUIRED means a consistency condition is unresolved. Preserve recovery files and inspect logs. Do not overwrite unknown files or start a second writer. Insufficient space requires removing idle staging or increasing the data volume before retrying.
"""),
]


def articles():
    renderer = MarkdownIt("commonmark", {"html": False})
    return [{"id": identifier, "title": title, "text": text, "html": renderer.render(text)}
            for identifier, title, text in ARTICLES]
