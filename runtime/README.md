# Native Runtime boundary

The Runtime contains pinned official Obsidian 1.13.7 and KasmVNC 1.5.0. It is a private
container running as UID/GID 10001, with all capabilities removed, no-new-privileges,
bounded memory/PIDs and no Docker socket, Core database, backup keys or provider keys.
Only the shared Vault parent, its own profile and three scoped Runtime credentials
are mounted. Mounting the parent lets a stopped editor reopen the current generation
after restore. KasmVNC is reachable through the authenticated Core Gateway.
The HTTP/WebSocket handshake also requires a private Kasm Basic credential injected
by Core. RFB's additional password exchange is disabled (`SecurityTypes=None`), so
that credential is never handed to the browser. Raw RFB TCP is not enabled.

Obsidian community plugins execute Node code by design. Electron runs with
`--no-sandbox` because its setuid helper cannot elevate under no-new-privileges;
the container is the isolation boundary. Existing plugins remain owner-controlled
opaque Vault data and are not audited or modified by Mastermind.

The supervisor accepts typed lifecycle operations only. It starts no editor until
Core completes startup recovery. External commits require Bridge buffer verification
and confirmed process termination. A missing Bridge with a running editor fails closed.
Subprocess output is not persisted because plugin output may contain private data.

Qualification of dirty-buffer handling, native rename, reconnect and the bounded
native regression is recorded in the implementation ledger. Eight-hour endurance
is excluded by the owner's acceptance decision; building an image is not test evidence.
