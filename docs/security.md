# Security and exposure

The service is non-indexable and access controlled. Nginx is the only public entry. All browser pages receive noindex/nofollow/noarchive; robots disallows crawling. There is no public Vault catalog, sitemap, feed, source map, debug/OpenAPI route or content discovery profile. Crawler/User-Agent/verification headers never grant privileges. Login and the minimal liveness response are deliberately reachable from any IP, subject to bounded rate/connection limits.

## Authority boundaries

| Principal | Allowed data and actions |
| --- | --- |
| Owner browser | Shell, native viewport, Vault operations, settings, Share management and accepted Crusher jobs |
| Share visitor | One sanitized note projection and explicitly granted edits with ETag |
| Public Crusher session | Own source acceptance and sanitized progress; no result, hierarchy context or private reader |
| Runtime/Bridge | Canonical Vault and own Runtime state; no Core database or provider/agent secrets |
| Worker | Current job source/chunks and private work directory; no canonical commit |
| Chronos reader | Minimal authenticated event card |
| Neptune | Own archive/mirror registration and independent read-only resource credential |
| Updater | Registered Mastermind head, verified group manifest, bounded sealed backup spool and recovery |

Owner Access Keys are exact opaque values, including Unicode, whitespace and newlines. No strength/composition/placeholder rules are imposed. Argon2id stores the verifier. Secure host-only HTTP cookies, same-origin CSRF enforcement, bounded sessions and ongoing Runtime authorization protect browser access. A capability is not interchangeable with an owner key. Restore and rotation invalidate the applicable live sessions.

## Secret ownership

Core resolves these bindings through Kernel; Register contains Volt references, not literal secrets:

| Core name | Kernel binding suffix below `services.mastermind.secrets.` |
| --- | --- |
| `ai_provider_key` | `ai_provider_key` |
| `chronos_service_token` | `chronos_service_token` |
| `share_pepper_v1` | `share_pepper_v1` |
| `recovery_identity` | `recovery_identity_v1` |
| `recovery_recipient` | `recovery_recipient_v1` |
| `backup_signing_private` | `backup_signing_private_v1` |
| `backup_signing_public` | `backup_signing_public_v1` |

Kernel bootstrap, service-local Runtime/Bridge/Worker credentials, initial owner key and typed host-agent tokens are private deployment files outside the Vault. Updater writes only the two Core Neptune control/export copies; producer credentials remain in the host agent's own private files. Exact credential readers reject unsafe file types and never trim a header token. Do not rotate a backup identity or Share pepper by discarding the prior recovery material. Preserve the required versioned keys and qualify the actual consumer before activation.

Existing Obsidian plugin secrets are explicitly excluded from Shell-secret migration/scanning. They remain inside opaque encrypted Vault backups. They never become permission to mount `.env`, provider keys or host-wide agent state into Runtime.

## Untrusted input and containment

Canonical filesystem resolution rejects traversal, symlinks, hardlinks and Unicode/path ambiguity at the operation boundary. Share rendering has no resource resolver. Public document/Git/web inputs stay in the bounded Worker sandbox; private-address DNS/redirect/subrequest checks apply before network fetches. Structured AI output cannot authorize existing-note writes or shell commands.

Worker contains only the extractors it actually invokes. Media is identified and streamed to the configured provider; there is no local FFmpeg/transcoding path. FFmpeg belongs only to the separate synthetic-video fixture image, which is never deployed as a service component. The JavaScript-page browser is the official stable Chrome for Testing archive pinned by version, byte count and SHA-256 in `worker-browser.lock.json`; the real-browser CI probe verifies its executable version and both JavaScript extraction and network isolation.

Images have fixed UID 10001, read-only roots, cap-drop ALL, no-new-privileges, CPU/RAM/PID limits and separate networks/mounts. Only Core has the host's narrow agent UDS mounts. Signed update manifests bind platform, three image digests, Bridge, Obsidian, model, schema and dependency tuple. Updater validates mount source **and target**, listener and component identity before stopping the service.

Detailed health, logs and admin controls are owner/private. `/healthz` returns only `{"status":"ok"}`; `/readyz`, `/internal`, `/api/internal` and `/v1` are blocked at public Nginx. Capability paths are redacted from its access log. Its native error log cannot redact arbitrary URI values, so this virtual host disables that unredacted stream and retains structured Core errors plus redacted request outcomes.

Release gates scan owned source, bundles and image layers for service secrets; original user Vault payloads are not part of those artifacts. No signed artifact or publication is accepted with an unresolved known-problem gate. See [releases](releases.md) and the exact [policy](policy/PART_07_SECURITY_AND_EXPOSURE_CONTROL.md).
