# API contracts

Production uses the canonical HTTPS origin. JSON errors expose stable sanitized `error.code`/`error.message`; malformed or oversized input, authentication failure, conflict and unavailable dependencies remain distinct. API collections have explicit page/limit bounds. There is no public OpenAPI endpoint. [Security](security.md) defines the principals, and [integration contracts](INTEGRATION_CONTRACTS.md) describe producer extensions.

## Browser surfaces

| Route family | Principal and contract |
| --- | --- |
| `/healthz`, `/robots.txt`, `/api/appearance` | Bounded public liveness, crawler policy and login appearance |
| `/api/auth/login`, `/api/auth/session`, `/api/auth/logout`, `/api/auth/rotate` | Exact Access Key, then owner cookie; unsafe operations require origin/CSRF |
| `/api/status`, `/api/notes`, `/api/note`, `/api/graph`, `/api/search/semantic`, `/api/index/semantic`, `/api/logs` | Owner-only status, bounded canonical/derived reads and managed writes |
| `/api/owner/settings`, `/api/owner/metrics`, `/api/owner/analytics`, `/api/owner/documentation`, `/api/owner/connection` | Authenticated operator state; settings use revision/conflict checks |
| `/api/owner/context-indexing/{settings,validate,initialize,waiting}` and `/jobs/{id}/resume` | Owner-only revision-bound configuration, validation, default initialization and explicit job resume; [contract](context-indexing.md) |
| `/api/owner/operations` and `/{id}/content`, `/confirm`, `/download` | Durable staged backup/portable/restore operations; stream actual size/hash and confirm destructive replacement |
| `/api/owner/agents` and `/agents/neptune/{enroll,initialization}` | Own-head lifecycle; setup code stays in memory, durable job identity survives restart |
| `/api/owner/updates`, `/api/owner/updates/check`, `/api/owner/updates/rollback` | Approved exact release discovery, recorded previous version and one typed whole-group operation |
| `/api/owner/resources` and `/resources/content` | Neptune scoped listing/metadata/content; single Range, ETag/If-Range, bounded streaming |
| `/runtime/index.html`, `/runtime/assets/*`, `/runtime/websockify` | Owner-only native gateway; ongoing session verification after WebSocket upgrade |
| `/api/v1/shares`, `/{id}` and `/{id}/link` | Owner creation/configuration/revocation and repeatable copy of a path-bound Share URL |
| `/s/{token}` and `/api/{policy,session,note}` beneath it | Share-specific public projection and granted edit capability; no resource access |
| `/api/v1/crusher/access` | Owner issues a one-use activation code |
| `/api/owner/gryphon`, `/bots`, `/connection`, `/link-challenge`, `/binding`, `/initialize`, `/management` | Owner-only Gryphon status and own-service linking; mutations require CSRF. Never accepts a bot token or caller-supplied service/adapter origin. |
| `/api/v1/crusher/sessions`, `/uploads`, `/jobs` | Scoped submission session or owner; public reads expose progress only |

Path/query identifiers are validated before use. Unsafe methods require the applicable CSRF/origin/capability checks even when the browser hides an action. `401/403` never turn into a successful empty result. A changed note ETag is a `409`; unsupported/unsatisfiable media ranges are rejected. Source uploads allow at most 2 GiB, recovery uploads at most 8 GiB, and actual streamed bytes are checked independently of Content-Length.

## Private interfaces

`POST /internal/gryphon/command` is the exact machine-authenticated exception to
the Nginx `/internal/` deny rule. It requires the Mastermind Gryphon credential
and a current matching private Telegram user/chat/connection identity from the
gateway. Envelopes are limited to 8 KiB. Repeated event IDs replay an encrypted,
transactional receipt; conflicting payloads receive 409. It cannot authorize
owner APIs or Vault reads. See [Gryphon](gryphon.md) for commands and deployment.

`POST /internal/bridge/related-notes` is a Bridge-authenticated, read-only
context-indexing lookup for the active Obsidian buffer. The body accepts `path`
(2 KiB), `text` (16 KiB), optional `focus` (4 KiB) and boolean `sampled`; its
encoded JSON limit is 128 KiB. The response contains `path`, up to eight
`items: [{path,title,excerpt,relation,reason}]`, `degraded` and `sampled`.
`relation` is `linked` or `similar`; `reason` explains the evidence without exposing
scores as probabilities. Only the original source is excluded before retrieval;
root, pool and templates follow the same evidence rules as all other notes, as
both sources and candidates. No role-specific empty response exists. Curator and generation
are disabled. One recommendation runs at a time; contention returns 429. Owner
cookies and public principals cannot authorize this route, and Nginx continues
to block the entire `/internal/bridge/` family. See [Related notes](mastermind-bridge.md#related-notes).

Semantic results use `representation: search-content.v1`: excerpts and `start`/`end`
refer to disposable normalized search text, not byte or character offsets in canonical
Markdown. `sha256` continues to identify the original Markdown. Clients must not use
these search offsets for writes.

Core `/internal/bridge/*` uses the own Bridge identity for managed native operations, Activity and bounded resources. `/api/internal/neptune/*` uses the separate export identity and purpose; the returned receipt binds generation, exact size and SHA-256. `/api/internal/updater/*` requires the own Updater control identity and retained request-bound write barrier. All are blocked by public Nginx.

`GET /internal/bridge/reference-dictionary` returns `current` (normalized name to display name), `history` (known internal names) and `saturn` (known resource paths) to the native Obsidian reference adapter. It requires the Bridge token and canonical readiness, and contains no note bodies or external contents. Owner cookies and other service identities do not authorize it. The removed private `/graph`, `/links` and `/graph-presentation` routes under `/internal/bridge` have no replacement drawing API: Obsidian owns those views. The owner `/api/graph` and underlying relation index remain available.

Runtime `/internal/*` accepts typed lifecycle/open/rename operations only. Worker accepts typed source/extraction/embedding and bounded local Curator status/assist requests only. Neither interface is mapped onto a host/public port. The same-container Core admin Unix socket serves doctor, validation, reindex, graph, operations and replication controls, with filesystem ownership as its separate local boundary.

Neptune `/api/v1/projects/mastermind/{resources,resource-metadata,resource-content}` requires the owner-purpose scoped local identity. Updater `/v1/heads/mastermind/{preparations,backup-spools}` binds immutable version, request ID and sealed spool ownership. Spool content streams directly; no base64 whole-archive body or caller-supplied host path is accepted.

The versioned [exposure inventory](exposure-inventory.json) lists every registered method/path, source, component, principal and exposure. Its source comparison rejects missing or stale entries. Negative tests enumerate owner routes and verify that an anonymous client cannot reach any of them; proxy coverage checks prevent a documented owner API from silently becoming an ingress 404. Family descriptions do not widen the allowlist. New routes must update this inventory, proxy profile, operator documentation and principal-boundary tests together.
