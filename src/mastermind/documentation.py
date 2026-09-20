"""Versioned, authenticated operator articles shipped with the implementation."""
from markdown_it import MarkdownIt

from . import __version__

ARTICLES = [
    ("introduction", "Introduction", """Mastermind keeps a canonical Obsidian Vault and the service state needed to operate it.
The owner uses Dashboard, Vault, Crusher, Shared and Settings. Documentation and Logout remain in the bottom navigation group.

### Your first session
Sign in with the exact Access Key. Spaces, Unicode and line breaks are significant. Paste preserves the exact clipboard value; Shift+Enter adds a line break. Enter submits. An empty Access Key is valid only if it was explicitly configured.
The service status checks availability independently of your key. A rejected key leaves the form open and returns focus to Access Key; it does not mean the service is unreachable. While a sign-in request is running, wait for its result before trying again.
An owner browser session lasts 12 hours. Ten owner sessions can coexist; Vault connects them to the same graphical Obsidian instance. Logging out closes that browser's Runtime connections. Access Key rotation ends the other sessions.

### Dashboard
CPU and RAM describe the server visible to the service. Disk describes the filesystem holding the canonical Vault, using space available to the service account. Uptime starts with the current Core process. Unknown or unavailable data are labeled explicitly.
Drag a card by its handle or drag a navigation row to reorder it. With a card handle or navigation link focused, Alt+Arrow Up or Down performs the same change. Navigation keeps its numbers and has no dot handles. Orders are saved on the server. In automatic sidebar mode, move the pointer to the left edge to reveal the menu; keyboard and mobile navigation remain available.
"""),
    ("vault", "Vault and references", """Vault opens the genuine Obsidian application through the authenticated Runtime gateway. Its themes, typography, dialogs and keyboard shortcuts follow Obsidian. Shell appearance does not rewrite Obsidian settings.

### First launch
A new Obsidian profile shows its native Vault trust prompt. Review the expected Vault and complete that prompt in the viewport. Mastermind preserves Obsidian's control of community plugins; it does not silently enable imported plugins. Runtime readiness stays pending until the verified Bridge loads. If the prompt was already completed and the Bridge is unavailable, use Reconnect and inspect the diagnostic status.

### Editing and navigation
Use the native editor, quick switcher and file manager. Mastermind Bridge adds internal `@note` references, autocomplete, reading and hover views, outgoing links, backlinks and a graph alongside native wikilinks. Markdown code, frontmatter and excluded HTML are not interpreted as references.
Use **Create note through Mastermind** and **Delete current note through Mastermind** in the native command palette for coordinated creation and deletion. Note basenames are unique across folders after Unicode normalization and case folding.
Native file-manager rename updates native links. Mastermind coordinates the operation and updates its own references. Folder moves preserve note names, attachments, empty subfolders and Share paths.

### External resources
Chronos references show the minimal permitted event card. Saturn resources are read through the local Neptune agent with owner authorization. A native Download command prepares an explicit download in the Vault toolbar. Shared visitors have no access to either resolver.

### Reconnect and fullscreen
Reconnect attaches to the existing graphical session. Fullscreen expands the Vault viewport; Exit fullscreen returns to the Shell. The graphical stream does not expose the native document as a web screen-reader tree.
The Vault toolbar contains Reconnect and Fullscreen. Use Settings → Backup for recovery snapshots; leaving the Vault tab does not close the native editor.
"""),
    ("crusher", "Crusher submissions", """Paste source links, one per line, or drop files anywhere on the unlocked page. You can also use Choose files. There is no source-type selector: YouTube links and recognized repository URLs are classified automatically; other HTTP(S) links are web sources. Submit links accepts up to twenty links at a time; a file selection accepts up to twenty files. A fullscreen accent outline and Upload here label identify an active file drag. Page colors follow Mastermind's current accent.
On a wide screen, processing history and search are on the left, with source links and file drop on the right. Both columns fit the space available beside the sidebar. Narrow screens stack the source form above the history. The page shows source identity, progress, stage and a sanitized failure message. The resulting note is found in Vault. Search filters the current page by source or stage. Clear search or Escape restores the full current page and keeps focus in the field.

### Owner and visitor access
On Dashboard, select Create & copy in the Crusher access card to create a six-digit one-time code valid for 30 minutes. A visitor opens `/crusher`, enters it in the centered access form and receives a 30-minute submission session. The unlocked page shows remaining submission time and service reachability. Receipts permit checking accepted jobs for 24 hours while they remain in the tab. The visitor cannot browse Vault or select private Saturn resources. Reloading the visitor page discards its in-memory session and receipts.

### Telegram access through Gryphon
In Settings → Gryphon Connection, initialize the scoped client if needed, then select **Link Mastermind function** and a ready registered bot. **Link Telegram account** displays a short-lived `/link CODE` command; send it privately to that bot. The card confirms the stable user and chat identity only after Gryphon verifies the binding. Bot tokens are never entered into Mastermind.
Send `/crusher` to receive a one-time code and the Crusher page URL. `/crusher_status` shows your active codes and sessions; `/crusher_revoke` revokes only your Telegram-issued access. Revoking the Telegram binding or unlinking the Mastermind function in Settings also invalidates this service's Telegram codes and sessions. Owner-created invitations, other services and the registered bot are unaffected. Existing accepted-job receipts remain progress-only until their own expiry.
When the gateway is unavailable, Retry status preserves the last verified identity. Shared gateway updates use the separate Gryphon version group and require confirmation of their effect on connected applications.

### Processing stages
QUEUED (0%) accepts a durable, idempotent job. ACQUIRING (5%) obtains or transfers its source into the isolated Worker. NORMALIZING (15%) is a checkpoint marking verified acquisition; extraction and normalization happen in the Worker. EXTRACTING (20%) obtains bounded text or prepares media. UNDERSTANDING (40%) asks Gemini for structured facts, topics and uncertainty. PLACING (55%) selects a branch. GENERATING (65%) writes a structured Markdown draft. VALIDATING (85%) checks its schema, size, secrets and forbidden references. COMMITTING (95%) rechecks the destination and writes the canonical note once. COMPLETED is 100%. Percentages are stage milestones, not an estimate of elapsed or remaining time.

### Context and destination
Context-indexing searches the authorized Vault locally using full-text, multilingual vectors, entities, metadata, graph neighbors and branch profiles. It combines and reranks the evidence, checks consistency and may perform one additional retrieval with the local Curator. The common search can find ordinary notes; only Crusher's placement policy restricts destinations to unambiguous branches reachable through root → #main → nested #key. Contradictory or insufficient evidence uses the configured pool. Scores are calibrated ranking scores, not probabilities.
Every new file is saved under root/crusher with a unique basename. The new note contains the verified link to its chosen branch or pool; parent notes are not rewritten. The default fallback is root/pool.md, connected from root. The default template is root/templates/example crusher.md. Settings → Obsidian & search combines the pool and template paths with the Curator switch and readiness checks. Curator is off by default; it runs locally without a provider key when enabled and available.
The selected source, structured understanding and bounded template structure reach the configured external generation provider. Retrieved Vault notes and branch profiles stay local. The template is captured when a job is accepted, so later edits affect subsequent jobs. Use its body and links placeholders; templates execute no Obsidian plugin scripts.

### Provider readiness
Production calls a selected Wyvern Adapter for the text and media functions. Wyvern sends Google's Gemini REST requests and resolves its provider credential through Kernel/Volt; Mastermind holds only its scoped Wyvern link. Configure the Adapter in the shared Updater TUI, then connect and select bindings in Settings → Wyvern. A healthy Core or configured Adapter alone does not prove live provider availability. Synthetic qualification verifies transport and storage, not real model quality or quota. Live acceptance requires a configured Adapter followed by a small non-sensitive end-to-end check.

### Limits and placement
Uploaded sources are limited to 2 GiB each. Uploads are hashed incrementally in a browser worker and checked by Core. The API also supports text up to 1 MiB and owner-authorized Saturn resources; these are not separate controls in the link/drop interface. Public URL fetching is restricted to validated public addresses; private network targets and arbitrary Git helpers are rejected.
One Crusher job runs at a time. Each job has a 60-minute deadline and at most three attempts per retryable stage. Context-indexing has a 90-second total budget, bounded evidence and at most one local Curator call. Invalid pool or template configuration pauses the job and releases the Worker. Correct it in Settings → Obsidian & search and explicitly resume with the current configuration; valid completed AI work is reused. A pool or template deleted and recreated at the same path must be explicitly rebound. Shared visitors cannot use context-indexing.
An interrupted operation resumes from durable checkpoints. Failed or unavailable source material must be resubmitted; a successful result is committed once. Wyvern owns provider credentials and transport; Mastermind owns prompts, placement, budgets and canonical commits.
"""),
    ("dashboard", "Dashboard and Activity", """Dashboard begins with CPU Usage, RAM Usage, Disk Usage and Uptime. Connectedness and Total items each occupy a 2x card. Activity Heatmap occupies a 4x card, and Crusher access occupies a 1x card. All cards can be reordered using their handles.

### Total items
Total items counts notes and other knowledge files in the canonical Vault, including images, documents, audio, video, canvases and other attachments. Folders, hidden files, trash and Obsidian plugin/configuration files are excluded. The card shows the note and attachment counts separately. It does not count service jobs, sessions or external resources that are not stored in the Vault.

### Crusher access
On the Dashboard's Crusher access card, select Create & copy to create a one-time upload code and copy it. The card shows the complete code and its expiration; Copied appears only after a successful clipboard write. Click the card again to copy the same code. If copying is unavailable, select the code manually or retry. The code stays in this owner's browser memory until expiry or logout; reloading the page clears the displayed value. It is not a login key for the Vault. See Crusher submissions for visitor permissions.

### Activity events
Only owner CREATE, EDIT, RENAME and MOVE actions count. Autosaves belong to one edit session. It closes when focus changes to another note, the note closes or 300 seconds pass after the last edit. A simultaneous rename and move contributes both events. Reading, navigation, indexing, public edits and automated Crusher writes do not count.
Events remain in UTC. Settings → Appearance → Activity timezone changes calendar grouping without rewriting history. Select up to 731 days. Day intensity is the count divided by the largest displayed count, with four nonzero levels. A single action on the only active day receives the brightest level.

### Connectedness
Native and Mastermind internal references form one undirected graph. Duplicate and self links do not increase its edges. For N notes and E distinct edges, Connectedness is `100 × 2E / (N × (N − 1))`; it is zero for fewer than two notes. External service links do not enter this percentage.
"""),
    ("shares", "Shared and public editing", """Open Shared to manage capability URLs for individual current notes. A Share has view or edit permission, optional password and optional expiry. It grants no directory, search, neighbor, attachment, graph or external-resource access. The canonical page is `/shared`; existing `/shares` bookmarks open the same page.

### Find and inspect
Search filters the current page immediately, ignoring case and query-edge whitespace while preserving the input text. Clear search or Escape restores that page. Name and Modified sort the current page; Modified is the note's file modification time, not its Share creation time. Expand a row with a click, Enter or Space to inspect password status, shared-since time, expiry, note size, permission, access status and full path. Missing-note metadata is shown as unavailable. No download count is invented for note sharing.

### Create and copy
Select Create Share and provide the note path, View or Edit access, optional expiry and optional password. Create share copies the URL and closes the overlay. If clipboard access is declined, the record opens with a selectable complete URL and Copy link remains available. Copy link works again after reload or a new login. Existing links remain valid when an owner obtains a new copy for an older record.
Passwords have no minimum length or complexity rule: even `1` is accepted. Empty means no password. Expiry can be up to 365 days ahead. When editing a policy, an empty password keeps the current one; Remove password turns it off. Policy changes invalidate existing visitor sessions. After confirmation, Revoke permanently disables that capability and its visitor sessions, removes the row from Shared and leaves the Vault note intact. An internal revocation record remains for access control and audit; the revoked URL cannot be revived.

### Public projection
Password-protected links first show a centered password form and service reachability. An unlocked page shows the note title followed immediately by its content. With Edit access, type directly into the Markdown text; there is no Edit button. Changes save after 900 milliseconds without typing, or with Ctrl/Cmd+S. Clean pages check for changes every five seconds. Links, references, frontmatter and protected content remain outside editable fields. The server rejects reference syntax and encoded bypasses before reconstructing Markdown.

### Simultaneous editing
The canonical Markdown file is the source of truth. Before accepting a public write, Mastermind pauses the native writer, flushes pending Obsidian edits and compares the file version with the visitor's version. A stale write is rejected instead of overwriting another edit. The current version appears above the retained unsaved draft, and automatic saving pauses. Copy the desired parts into the editor, then select Save merged changes. Further conflicts require another review. Text typed during a save or background refresh is retained. Unsaved drafts live only in the open tab; closing it discards them after the browser's unsaved-changes warning.
Accepted edits are journaled into the canonical Vault and reindexed in SQLite. Obsidian sees the same file; public editing does not add owner Activity events.
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
Snapshots include this service's non-secret Wyvern Adapter/profile choices and scoped identity, without link tokens, provider keys or shared configuration. Restore marks configured choices pending verification; inference waits for matching authoritative bindings or explicit selection in Settings → Wyvern. Restore never edits shared Wyvern state. Legacy snapshots retain the target's existing choices. An unavailable previously configured Wyvern link prevents a new snapshot rather than silently omitting those choices.

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


TOPICS = {
    "introduction": ("Getting started", "Sign in, navigate the service and arrange your workspace.", ["login", "Access Key", "navigation", "search"]),
    "vault": ("Knowledge base", "Edit notes and resources in native Obsidian.", ["Obsidian", "references", "Reconnect", "Fullscreen"]),
    "dashboard": ("Knowledge base", "Read service metrics, total items, connectedness and daily activity.", ["Total items", "attachments", "Activity Heatmap", "Crusher access", "Create access code"]),
    "crusher": ("Knowledge base", "Submit a source and follow its processing stages.", ["Submissions", "Clear search", "source", "access code"]),
    "shares": ("Knowledge base", "Inspect shared notes, change policies and revoke visitor access.", ["Shared", "Create Share", "Copy link", "password", "revoke", "Modified"]),
    "settings": ("Operations", "Manage appearance, the Access Key and the Kernel connection.", ["Appearance", "Security", "timezone", "Volt"]),
    "backup": ("Operations", "Create encrypted snapshots and restore a verified recovery archive.", ["Backup", "Restore", "Neptune", "mirror"]),
    "updates": ("Operations", "Apply verified releases and recover interrupted updates.", ["Updater", "rollback", "recovery"]),
    "logs": ("Operations", "Read diagnostic logs and resolve unavailable dependencies.", ["Logs", "troubleshooting", "NOT_READY"]),
}


def articles():
    renderer = MarkdownIt("commonmark", {"html": False})
    source = {identifier: (title, text) for identifier, title, text in ARTICLES}
    result = []
    for identifier, (group, summary, keywords) in TOPICS.items():
        title, text = source[identifier]
        html = renderer.render(text).replace("<h3>", "<h4>").replace("</h3>", "</h4>")
        result.append({"id": identifier, "title": title, "text": text, "html": html,
                       "group": group, "summary": summary, "keywords": keywords, "version": __version__})
    return result
