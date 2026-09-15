# API contracts

Production uses the canonical HTTPS origin. JSON errors expose stable sanitized `error.code`/`error.message`; malformed or oversized input, authentication failure, conflict and unavailable dependencies remain distinct. API collections have explicit page/limit bounds. There is no public OpenAPI endpoint. [Security](security.md) defines the principals, and [integration contracts](INTEGRATION_CONTRACTS.md) describe producer extensions.

## Browser surfaces

| Route family | Principal and contract |
| --- | --- |
| `/healthz`, `/robots.txt`, `/api/appearance` | Bounded public liveness, crawler policy and login appearance |
| `/api/auth/login`, `/api/auth/session`, `/api/auth/logout`, `/api/auth/rotate` | Exact Access Key, then owner cookie; unsafe operations require origin/CSRF |
| `/api/status`, `/api/notes`, `/api/note`, `/api/graph`, `/api/search/semantic`, `/api/index/semantic`, `/api/logs` | Owner-only status, bounded canonical/derived reads and managed writes |
| `/api/owner/settings`, `/api/owner/metrics`, `/api/owner/analytics`, `/api/owner/documentation`, `/api/owner/connection` | Authenticated operator state; settings use revision/conflict checks |
| `/api/owner/operations` and `/{id}/content`, `/confirm`, `/download` | Durable staged backup/portable/restore operations; stream actual size/hash and confirm destructive replacement |
| `/api/owner/agents` and `/agents/neptune/{enroll,initialization}` | Own-head lifecycle; setup code stays in memory, durable job identity survives restart |
| `/api/owner/updates`, `/api/owner/updates/check`, `/api/owner/updates/rollback` | Approved exact release discovery, recorded previous version and one typed whole-group operation |
| `/api/owner/resources` and `/resources/content` | Neptune scoped listing/metadata/content; single Range, ETag/If-Range, bounded streaming |
| `/runtime/index.html`, `/runtime/assets/*`, `/runtime/websockify` | Owner-only native gateway; ongoing session verification after WebSocket upgrade |
| `/api/v1/shares` and `/{id}` | Owner creation/configuration/revocation of a path-bound Share |
| `/s/{token}` and `/api/{policy,session,note}` beneath it | Share-specific public projection and granted edit capability; no resource access |
| `/api/v1/crusher/access` | Owner issues a one-use activation code |
| `/api/v1/crusher/sessions`, `/uploads`, `/jobs` | Scoped submission session or owner; public reads expose progress only |

Path/query identifiers are validated before use. Unsafe methods require the applicable CSRF/origin/capability checks even when the browser hides an action. `401/403` never turn into a successful empty result. A changed note ETag is a `409`; unsupported/unsatisfiable media ranges are rejected. Source uploads allow at most 2 GiB, recovery uploads at most 8 GiB, and actual streamed bytes are checked independently of Content-Length.

## Private interfaces

Core `/internal/bridge/*` uses the own Bridge identity for managed native operations, Activity and bounded resources. `/api/internal/neptune/*` uses the separate export identity and purpose; the returned receipt binds generation, exact size and SHA-256. `/api/internal/updater/*` requires the own Updater control identity and retained request-bound write barrier. All are blocked by public Nginx.

Runtime `/internal/*` accepts typed lifecycle/open/rename operations only. Worker accepts typed source/extraction/embedding requests only. Neither interface is mapped onto a host/public port. The same-container Core admin Unix socket serves doctor, validation, reindex, graph, operations and replication controls, with filesystem ownership as its separate local boundary.

Neptune `/api/v1/projects/mastermind/{resources,resource-metadata,resource-content}` requires the owner-purpose scoped local identity. Updater `/v1/heads/mastermind/{preparations,backup-spools}` binds immutable version, request ID and sealed spool ownership. Spool content streams directly; no base64 whole-archive body or caller-supplied host path is accepted.

The versioned [exposure inventory](exposure-inventory.json) lists every registered method/path, source, component, principal and exposure. Its source comparison rejects missing or stale entries. Negative tests enumerate owner routes and verify that an anonymous client cannot reach any of them; proxy coverage checks prevent a documented owner API from silently becoming an ingress 404. Family descriptions do not widen the allowlist. New routes must update this inventory, proxy profile, operator documentation and principal-boundary tests together.
