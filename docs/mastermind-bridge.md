# Obsidian Runtime and Bridge

Runtime packages the official Obsidian 1.13.7 AppImage, pinned KasmVNC 1.5.0, Openbox and the release-owned TypeScript Bridge. It runs as UID/GID 10001, with no capabilities, no host network, a read-only root and only its own Vault/profile mounts. Obsidian self-update is disabled in its owned Runtime profile; an Obsidian version change belongs to a qualified whole-service release.

Native UI, themes, layout, shortcuts, plugin settings and file management follow Obsidian. Bridge uses native CSS variables and UI primitives. Shell appearance does not modify the editor. On a new native profile, the owner completes Obsidian's trust prompt; Mastermind does not silently rewrite browser storage to enable imported plugins. A release is ready only after the Bridge handshake.

## Managed behavior

Bridge supplies `@note` autocomplete, resolution and hover; Chronos/Saturn cards and resource handling; outgoing/backlink panes; and a graph containing the unified internal relation model. Native wikilinks remain native. Unresolved historical targets remain broken after reindex. Code, comments, frontmatter, email and other grammar exclusions share the Core/TypeScript fixture contract. Offsets are translated from Unicode code points into CodeMirror UTF-16 coordinates.

Use the native command palette's **Create note through Mastermind** and **Delete current note through Mastermind** commands. Rename/move coordinates native `FileManager.renameFile` and recognized `@` references. The required native “Automatically update internal links” preference must be enabled. Unknown external/plugin writes remain possible within Obsidian's inherited trust model; validation detects unsupported states and blocks later managed writes rather than pretending they passed preflight.

## Process and transport lifecycle

The supervisor permits only fixed typed operations for the pinned editor and its own Vault. Quiescence saves and verifies dirty buffers; the supervisor checks the entire descendant process tree before allowing a filesystem generation change. Adopted/double-forked plugin writers block mutation. A failed Bridge handshake cannot authorize a parallel writer.

The browser reaches KasmVNC only through Core's authenticated owner gateway. Logout, key rotation and session expiry revoke an existing WebSocket, including after the initial upgrade. The upstream KasmVNC connection does not use WebSocket Ping because the qualified server does not answer it; owner authorization is still revalidated continuously. Reconnect and full-screen retain native behavior.

## Portable export

Download Vault copy produces a filesystem copy, preserving original user files. Its own Bridge area contains a credential-free reference-history snapshot. The copy opens in standard pinned Obsidian outside Mastermind. Native Markdown/wikilinks remain readable without Bridge; custom `@` behavior requires Bridge. There is no synchronization back from the exported copy.

Compatibility tests cover actual keyboard edits, dirty-buffer preservation, native rename propagation, resource reading, reconnect/revocation and sustained native saves. Unit peers are not evidence that the real editor passed; see [verification status](IMPLEMENTATION.md).
