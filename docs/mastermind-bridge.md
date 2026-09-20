# Obsidian Runtime and Bridge

Runtime packages the official Obsidian 1.13.7 AppImage, pinned KasmVNC 1.5.0, Openbox and the release-owned TypeScript Bridge. It runs as UID/GID 10001, with no capabilities, no host network, a read-only root and only its own Vault/profile mounts. Obsidian self-update is disabled in its owned Runtime profile; an Obsidian version change belongs to a qualified whole-service release.

Native UI, themes, layout, shortcuts, plugin settings and file management follow Obsidian. Bridge uses native CSS variables and UI primitives. Shell appearance does not modify the editor. On a new native profile, the owner completes Obsidian's trust prompt; Mastermind does not silently rewrite browser storage to enable imported plugins. A release is ready only after the Bridge handshake.

Runtime joins the internal service network and a dedicated `runtime-egress`
bridge for outbound DNS/HTTPS. This lets native community-theme/plugin catalogs,
downloads and the owner's existing plugin network behavior work. Runtime has no
published host ports; owner access still passes through authenticated Core.
This egress does not grant Runtime the Core/Worker credentials or change the
Worker's separate source-fetch policy. Native self-update remains disabled.

## Managed behavior

Bridge supplies `@note` autocomplete, resolution and hover, and Chronos/Saturn cards and resource handling. The native **Graph view**, **Local graph**, **Backlinks** and **Outgoing links** include recognized `@` references. There are no separate Mastermind graph/link panes or commands. Restored legacy panes are converted to their native counterparts.

`@note` points to the existing note. `@chronos: id` and `@saturn: root/path` become virtual external targets with readable labels; clicking them, including through the context menu, opens the existing resource modal. They have no local file, so the native graph's **Existing files only** filter hides them. Graph search, grouping, depth and layout otherwise follow Obsidian. This does not copy the contents of either external service into the Vault.

Original Markdown, native wikilinks and the persisted native metadata remain unchanged. Bridge augments native metadata reads in memory, using the same Core/TypeScript grammar and precise UTF-16 source positions for backlink snippets. It leaves the raw reference iterator used by Obsidian's rename writer untouched; the existing managed or portable rename path updates `@` text. Code, comments, frontmatter, email and other grammar exclusions remain excluded. Historical deleted targets remain broken links. Disabling Bridge removes its contribution and restores native methods without changing note files.

The adapter uses private Obsidian metadata/graph hooks, qualified on **1.13.7**. On another version it disables this integration and displays a notice; a new version needs a fresh native qualification. Core plugins Graph, Backlinks and Outgoing links must be enabled to use those views.

Managed Bridge reads the names/history dictionary from the Bridge-only `/internal/bridge/reference-dictionary` route at startup, on structural changes and every ten seconds. Source edits are debounced and parsed locally, one changed note at a time. Name/history changes reindex the Vault because they can change recognition of previously plain text. Only notes with recognized `@` links have extra cache entries; no second graph, node-position store, full-text store or force simulation is maintained. Native graph options live in Obsidian's own profile. The old Bridge graph/link/presentation endpoints and portable graph cache have been removed. Core's derived relation index and owner `/api/graph` remain in use for analytics.

Use the native command palette's **Create note through Mastermind** and **Delete current note through Mastermind** commands. Rename/move coordinates native `FileManager.renameFile` and recognized `@` references. The required native “Automatically update internal links” preference must be enabled. Unknown external/plugin writes remain possible within Obsidian's inherited trust model; validation detects unsupported states and blocks later managed writes rather than pretending they passed preflight.

## Related notes

The **Related notes** ribbon button (lightbulb) or **Mastermind Bridge: Open related
notes** command opens a native right sidebar pane. It follows the active Markdown
note and shows up to eight suggestions with short excerpts. Click a suggestion
to open it; Ctrl/Cmd-click opens a new tab. This is a read-only discovery pane and
does not insert links or change note text.

The managed Bridge sends bounded context from the current editor buffer to
`POST /internal/bridge/related-notes`, including unsaved changes. After 1.2 seconds
without a change it requests recommendations; requests never overlap and have a
minimum 1.5-second gap after completion. Newer buffers or tabs invalidate older
responses. An open pane also refreshes unchanged content every 30 seconds so
index changes can appear. Hidden, closed, empty or paused panes stop requests.
Long notes contribute sampled beginning/middle/end passages and a cursor-local
window; the pane explicitly identifies sampled context.

Core reuses the common [context-indexing](context-indexing.md) knowledge lookup:
local E5, FTS, metadata/entities and graph expansion followed by reranking. The
current source is excluded before channel limits. Root, pool and templates remain
eligible, both as sources and candidates, with the same content requirements.
Each card distinguishes an explicit link from content similarity and includes a short
reason and a cleaned evidence excerpt. There is no minimum number of cards: the pane
can abstain when it finds insufficient evidence, regardless of the note's role.
Graph-only matches without topical evidence are omitted. Curator and Crusher's
placement/generation policy do not run. Search can return lexical suggestions
with an incomplete-search notice while vectors are unavailable or rebuilding.
There is one recommendation slot in Core and no unbounded inference queue.

The input is not saved as note content or raw query history, and retrieved notes
remain local. Portable mode displays an explanation because it has no Core
context-indexing connection. Native UI qualification is available through
`scripts/qualify_related_notes.py`, using synthetic notes and actual local E5;
it does not alter or deploy the owner's running Vault.
The latest [quality regression report](related-notes-quality.md) covers template noise,
scope, directory relocation, multilingual retrieval and placement compatibility.

## Process and transport lifecycle

The supervisor permits only fixed typed operations for the pinned editor and its own Vault. Quiescence saves and verifies dirty buffers; the supervisor checks the entire descendant process tree before allowing a filesystem generation change. Adopted/double-forked plugin writers block mutation. A failed Bridge handshake cannot authorize a parallel writer.

The browser reaches KasmVNC only through Core's authenticated owner gateway. Logout, key rotation and session expiry revoke an existing WebSocket, including after the initial upgrade. The upstream KasmVNC connection does not use WebSocket Ping because the qualified server does not answer it; owner authorization is still revalidated continuously. Reconnect and full-screen retain native behavior.

## Portable export

The owner portable-export API produces a filesystem copy, preserving original user files. The Vault tab exposes only Reconnect and Fullscreen; it no longer offers a portable-export button. Its own Bridge area contains a credential-free reference-history snapshot. The copy opens in standard pinned Obsidian outside Mastermind. With Bridge enabled on 1.13.7, native graphs and link panes retain the `@` integration using local names and that history. External nodes remain visible, but live Chronos/Saturn cards require the managed service connection and show unavailable in a portable copy. Native Markdown/wikilinks remain readable without Bridge; custom `@` behavior requires Bridge. There is no synchronization back from the exported copy.

Compatibility tests cover actual keyboard edits, dirty-buffer preservation, native rename propagation, resource reading, reconnect/revocation and sustained native saves. Unit peers are not evidence that the real editor passed; see [verification status](IMPLEMENTATION.md).
