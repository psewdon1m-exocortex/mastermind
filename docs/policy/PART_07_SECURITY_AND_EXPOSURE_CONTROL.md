# Part 07. Security, Secret Handling And Exposure Control

> This is a normative component of the
> [Part 00 documentation authority](./PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md).

This part defines how to keep credentials and private data out of CI, release
artifacts and deployment output, and how to minimize discovery of services by
crawlers and automated probes when the product requires a private or concealed
exposure model. It complements the deployment, release, logging, backup and
SEO/GEO guides; it does not replace their domain-specific rules.

The words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT** and **MAY** are
normative. Numeric limits MUST be derived from measured workload and threat
model, enforced at runtime and tested at their boundary.

## Mandatory Material-Divergence Protocol

Before implementation, compare this guide with the target system's current CI,
runner permissions, secret sources, artifact contents, deployment process,
network exposure, authentication, crawler policy, edge rules, logs and
operator workflow. A difference is **material** when it changes a trust
boundary, credential flow, granted permission, public reachability, indexing
or automation policy, data/API contract, release provenance, runtime behavior,
compatibility, incident response, migration or rollback.

If a material difference is found, the implementer MUST:

1. pause the affected decision while continuing only independent work;
2. notify the operator before implementing the divergent behavior;
3. provide the applicable rule, observed implementation with file/configuration
   or runtime evidence, exact difference, security/user/operations impact,
   options, recommendation, migration, rollback and verification plan;
4. explicitly ask how to proceed;
5. obtain additional explicit operator confirmation and record the decision
   before resuming the affected work.

Project-local documentation never overrides this Part. Existing runtime
behavior remains evidence that may require a migration decision, not an
alternative security policy. Follow the complete reporting and decision rules
in [Part 00](./PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md#1-mandatory-material-divergence-protocol). If an active leak or exposed control plane is discovered, report it as
urgent and perform only already authorized, reversible containment until the
operator decides.

## 42. Security Model And Data Classification

### 42.1 Security objectives

The implementation MUST preserve all of these properties:

- CI can build and test untrusted changes without exposing production secrets;
- release artifacts contain only intentional, reviewed, reproducible content;
- deployment receives the minimum secrets required at the latest possible
  moment;
- no secret is printed, cached, uploaded or retained as an accidental side
  effect;
- every deployed artifact is tied to a reviewed source revision and verified
  publisher identity;
- private services are unreachable without the intended network and identity
  controls;
- crawler declarations and anti-probing controls are generated from one
  versioned policy and tested together;
- security failures are observable without logging the sensitive material.

### 42.2 Classify before automating

Every value entering CI or deployment MUST have an owner, classification,
allowed consumers, delivery mechanism, rotation procedure and retention rule.

| Class | Examples | CI/deployment rule |
| --- | --- | --- |
| Public | Published version, public URL, public key | May appear in artifacts and logs after review |
| Internal | Topology labels, non-public hostnames, feature rollout data | Limit to necessary jobs and operator output |
| Confidential | Customer records, private source, backup contents | Never place in public artifacts; use least-privilege access |
| Secret | Tokens, passwords, private keys, session-signing material | Inject at runtime; never commit, print, cache or package |
| Regulated/high impact | Recovery keys, production datasets, identity exports | Separate approval, access logging, encryption and retention policy |

Names are not protection. A value called `configuration` may still be a bearer
secret; a public key is not secret merely because it contains `key` in its
name. Classification follows impact if disclosed.

### 42.3 Draw the trust boundaries

At minimum, model these as separate principals:

1. source contributor;
2. pull-request validation job;
3. trusted release job;
4. artifact registry;
5. deployment controller;
6. target runtime identity;
7. operator;
8. public edge or private access gateway.

A principal MUST NOT inherit credentials merely because it runs in the same CI
system. Promotion between boundaries requires an authenticated artifact,
explicit policy and auditable authorization.

## 43. Preventing Secret Leakage In CI

### 43.1 Split untrusted validation from trusted publication

Pull-request jobs MUST be treated as execution of untrusted code. They MUST
NOT receive production credentials, signing keys, deployment tokens or a
general-purpose repository write token. This includes contributions from
forks, dependency-generated changes and tests that can modify build scripts.

Use separate workflows and identities:

- **validation:** read-only source, no production secrets, no deployment
  permission, isolated test dependencies;
- **release:** runs only for the approved protected trigger after required
  checks, with narrowly scoped artifact-publication permission;
- **deployment:** consumes an already published immutable release and requires
  its own environment approval and identity.

Do not let a release job execute scripts from an untrusted branch after secrets
become available. Re-check that the source revision is the reviewed protected
revision before credential issuance.

### 43.2 Prefer short-lived identity

Use workload identity federation or another short-lived, audience-bound
credential exchange instead of static cloud and registry tokens. Bind the
issued credential to repository, workflow, protected ref, environment and
intended audience. Grant only required operations and a short lifetime.

If a static secret is unavoidable:

- store it only in the CI secret facility;
- scope it to one environment and minimum resource set;
- protect the environment with explicit approval;
- rotate it on schedule and immediately after suspected exposure;
- record the owner and last verification date;
- provide a tested revocation path.

Secret masking is defense in depth, not permission to print a secret. Masking
often misses transformed, encoded, split, multiline or structured variants.

### 43.3 Runner isolation

- Prefer ephemeral runners destroyed after one job.
- Never run untrusted changes on a persistent runner that also handles
  production deployment.
- Isolate jobs by operating-system account, container or VM and network policy;
  a workspace directory alone is not isolation.
- Remove credentials from the environment before executing third-party tests or
  package hooks that do not require them.
- Block access to cloud instance metadata and unrelated internal services.
- Avoid privileged containers and host container-engine sockets. Possession of
  the engine socket is normally equivalent to host control.
- Clear temporary files, credential helpers and agent sockets at job end; do
  not rely on workspace cleanup to erase a compromised persistent host.

### 43.4 Workflow and dependency integrity

Third-party CI actions, images, package managers and build tools execute code.
Pin them to immutable commit or image digests, review requested permissions and
update them through a controlled dependency process. Tags alone are mutable.

Set the workflow token to no permissions by default, then grant the minimum per
job. Protect release tags and environments. Require review for changes to CI,
release, deployment, dependency-lock and security-policy files.

Prevent dependency confusion with locked sources, expected package namespaces,
checksums and registry allow-lists. Network access during a release build
SHOULD be limited to declared dependency and artifact endpoints.

### 43.5 Safe secret use inside a job

Secrets MUST NOT be passed in command-line arguments because process listings,
shell tracing and error output may reveal them. Prefer a short-lived protected
file descriptor, secret mount, credential helper or standard input when the
consumer supports it.

The job MUST:

- disable command tracing around secret operations;
- avoid dumping the environment, complete HTTP requests, generated deployment
  configuration or authentication debug output;
- quote input and avoid evaluating data as shell code;
- create temporary secret files with restrictive permissions in an isolated
  temporary directory;
- delete or unmount them immediately after use;
- redact recursively in structured logs and bound diagnostic payloads;
- ensure failure handlers and post-job hooks follow the same rules.

Be especially careful with commands that render fully substituted deployment
configuration: their ordinary diagnostic output may contain every injected
secret. Validate such output in a protected process and print only a redacted
summary.

### 43.6 Build containers without baking secrets

Do not use image build arguments, copied environment files, package-manager
configuration or ordinary `RUN` environment variables for secrets. Deleting a
file in a later layer does not remove it from earlier layers.

Use build-time secret mounts that are not committed to layers, and keep network
credentials scoped to the one instruction that needs them. The final image
MUST be scanned and inspected by layer, not only by its visible filesystem.
Use an explicit build context allow-list or exclusion file so repositories,
environment files, SSH material, backups, database dumps, editor history and
local artifacts cannot enter the context accidentally.

### 43.7 Caches, artifacts and logs

- Cache keys and paths MUST NOT contain secrets.
- Never cache a home directory, credential directory or broad workspace root.
- Cache restore from untrusted branches MUST NOT overwrite trusted executable
  locations used by release jobs.
- Test reports, coverage, traces, screenshots, browser videos, core dumps and
  heap dumps are artifacts and require the same data review as binaries.
- Artifact upload MUST use an explicit file list, not an unrestricted workspace
  glob.
- Retention and reader permissions MUST be declared for every artifact class.
- Public releases MUST NOT include source environment files, internal backups,
  private source maps, debug databases, repository metadata or local logs.

Run secret and high-risk-file scanning before artifact publication and again
on the final archive or image. A scanner finding is a release failure until it
is reviewed; an allow-list entry requires owner, reason and expiry.

## 44. Secure Release Publication

### 44.1 Build once, promote the same bytes

Build a candidate once, test those exact bytes and promote them without
rebuilding per environment. Bind the release to:

- source revision;
- semantic version;
- artifact role and platform;
- cryptographic digest;
- dependency lock and software bill of materials;
- build provenance and builder identity;
- compatibility requirements.

The release manifest MUST be authenticated by a digital signature or trusted
attestation rooted in a key already trusted by the consumer. A digest copied
from the same unauthenticated channel as the artifact detects corruption but
does not prove who published it.

### 44.2 Signing-key isolation

Every service has a separate private release-signing key in protected GitHub
Secrets. Only the tag-triggered signing job may receive it. The job may stage
the key only in a restricted temporary file or isolated signing process for the
minimum signing interval; it MUST delete that material before artifact upload
and MUST NOT cache, print or preserve the workspace. Pull-request and ordinary
branch jobs receive no signing secret.

Release CI derives the public counterpart and exports only that public value.
It embeds the public key in the service's versioned `bootstrap.sh`, scans every
output for private-key material and verifies the produced signature using the
derived public key. Upload and signing permissions remain separate. Audit logs
record service, source revision, artifact digest, signing result and policy
revision, never key material.

### 44.3 Publication gate

Before publication, fail closed on:

- incomplete tests or security checks;
- unreviewed workflow changes;
- secret-scanner findings;
- unexpected files or executable permissions;
- manifest/artifact digest mismatch;
- unsigned or unverifiable provenance;
- critical dependency or image-policy violations under the approved policy;
- version/source mismatch;
- an artifact built from a different revision than the protected release
  trigger.

Publication is a distinct state transition. Uploading a candidate to temporary
storage is not proof that it is an approved release.

## 45. Preventing Leakage During Deployment

### 45.1 Deployment identity and input

The deployment controller MUST receive only an immutable version or manifest
reference, never an arbitrary command, image name or download URL from a web
client. It independently resolves approved artifacts, verifies signature,
digest, role, version and compatibility, then applies them.

Use a separate least-privilege deployment identity. A web application MUST NOT
possess host root credentials or the container-engine socket. Privileged local
operations belong in a small, authenticated controller with a fixed operation
set and strict input validation.

### 45.2 Runtime secret delivery

Runtime secrets are injected after artifact verification and as close as
possible to process start. Prefer mounted secret files or an identity-based
secret manager. If an environment file is required:

- create it outside source and release directories;
- allow access only to the deployment/runtime account;
- separate operator-editable non-secret values from machine-owned secrets;
- validate required fields without printing their values;
- never include the file in backup, support bundles or release archives;
- rotate credentials independently of the artifact version.

Do not write secrets into generated frontend assets, HTML, health responses,
diagnostic endpoints, process titles, labels or image metadata. A frontend
cannot keep a delivered value secret.

#### 45.2.1 Authenticated Runtime Credential Changes

Part 01 permits two narrow Settings workflows: changing the single-operator
Access Key and rotating a control-plane access token. This does not authorize general
secret administration from the browser.

An Access Key change MUST:

1. require an authenticated session, CSRF protection and recent proof of the
   current Access Key;
2. receive the new key twice and compare it without logging either value;
3. require an explicitly supplied value but apply no minimum/maximum length,
   strength/entropy, character-set, URL-safe/ASCII, breached/dictionary,
   example/placeholder or other password-style policy;
4. create a new salted verifier with the approved password-hashing KDF;
5. replace the verifier atomically;
6. revoke every other active browser session and rotate affected session state;
7. write an audit event containing actor, time and outcome but no key material.

Every Access Key boundary MUST preserve the operator's exact value without
trimming, normalization, case folding or silent truncation. This absence of a
credential-composition policy does not relax constant-time verification,
rate limiting, secure transport, verifier protection, session expiry, CSRF or
reauthentication requirements.

A control-plane token change MUST:

1. use an authenticated, CSRF-protected, rate-limited endpoint scoped only to
   control-plane credential replacement;
2. accept the replacement in a write-only field that begins empty and is never
   returned by any read API;
3. keep the value out of frontend state persistence, URLs, telemetry, errors,
   logs, clipboard automation and backup;
4. validate the new credential against the already validated control-plane identity
   over authenticated transport;
5. activate the new secret atomically only after validation, retaining or
   restoring the previous credential on failure;
6. expose only configured/not-configured, public peer identity, reachability and
   a non-secret configuration revision to the UI;
7. audit the rotation outcome without token, suffix or reversible fingerprint.

The backend may delegate the write to a least-privilege local secret controller.
The web application MUST NOT gain arbitrary filesystem, environment-file,
container-engine or host-root access as a consequence.

### 45.3 Safe deployment execution

Deployment MUST:

1. verify publisher identity and every artifact digest;
2. validate configuration without emitting substituted secrets;
3. create a verified backup when the change can mutate authoritative state;
4. pull all immutable artifacts before switching the live version;
5. apply database changes under the documented compatibility contract;
6. start with least privilege, read-only filesystem and bounded writable
   mounts where supported;
7. gate success on authenticated readiness and functional smoke checks;
8. roll back through a tested path on failure;
9. retain bounded, redacted diagnostics and an audit record.

Temporary archives and decrypted material MUST live in a size-bounded protected
directory, be verified before extraction, resist path traversal, links and
decompression bombs, and be removed after success or rollback. Never log a
complete environment or deployment request when reporting failure.

### 45.4 Runtime boundary

- Run as a dedicated non-root identity.
- Drop capabilities and apply a restrictive system-call profile.
- Mount the root filesystem read-only where practical.
- Allow writes only to named data and temporary locations with quotas.
- Keep databases and control APIs on private networks.
- Permit egress only to documented dependencies.
- Bind application ports to the intended interface; do not rely on an
  application login to compensate for an accidentally public database or
  administrator port.
- Separate health endpoints into liveness and readiness and disclose no
  versions, topology, secrets or dependency credentials to unauthenticated
  callers.

## 46. Exposure Modes

Choose one exposure mode for every route and listener. "Mostly private" is not
a mode.

| Mode | Reachability | Search/automation policy | Typical use |
| --- | --- | --- | --- |
| Public/indexable | Internet reachable | Explicitly allow approved discovery | Public content |
| Public authenticated/non-indexable | Internet reachable from every client IP; protected content requires application authentication | `noindex` plus edge controls; no operator data before auth | Sign-in and browser operator application |
| Private | Reachable only through identity-aware gateway, VPN, mTLS or network allow-list | Deny automation by default | Machine control APIs and internal infrastructure |
| Concealed | No public listener or route; private DNS/network and default-deny firewall | No crawler contract because traffic cannot reach the service | High-sensitivity control planes |

For maximum concealment, the strongest control is to make the service
unreachable from the public Internet. An obscure hostname, non-standard port,
unlinked page, `robots.txt`, `noindex` or hidden menu item does not create a
security boundary.

The standard browser operator profile is `public authenticated`. Its canonical
login page is reachable from every source IP. `OPERATOR_CIDR`, an equivalent
source-IP allow-list and a mandatory VPN are forbidden as prerequisites for
sign-in. Access Key verification establishes the operator identity; Secure,
HttpOnly, bounded application sessions carry it afterwards, and every protected
API authorizes the session. Nginx provides TLS, request normalization, rate
limits and probe rejection but MUST NOT grant data access based on client IP.
Trusted-proxy ranges identify only the server-managed Nginx hop and do not limit
which users may reach the login page.

When feasible, use this order:

1. no public address, listener or route;
2. private network or authenticated tunnel;
3. identity-aware gateway or mutual TLS;
4. source network allow-list where identities are unavailable;
5. application authentication and authorization;
6. edge rate limits and anomaly controls;
7. indexing directives only as publication metadata.

## 47. Unified Bot Policy

### 47.1 One versioned policy source

Do not maintain crawler decisions independently in the application,
`robots.txt`, reverse proxy, WAF and documentation. Define a versioned Bot
Policy Registry and generate enforcement and tests from it.

```yaml
version: "<policy revision>"

purposes:
  classic_search: allow_public_only
  ai_search: allow_public_only
  user_fetch: allow_public_only
  model_training: deny
  unknown_automation: rate_limit_then_challenge

zones:
  public:
    classification: public
    discovery: allow
  authenticated:
    classification: public_authenticated
    enforcement: authentication
    automation: deny
  concealed:
    classification: restricted
    enforcement: private_network_and_identity
    automation: deny
```

Generate from the registry:

- `robots.txt` for intentionally public hosts;
- edge, gateway and WAF rules;
- route-classification and verification fixtures;
- monitoring labels and alert expectations;
- operator documentation;
- a policy-change log with approver and rationale.

A search crawler and a model-training crawler from the same provider may serve
different purposes and MUST NOT inherit the same permission automatically.

### 47.2 What robots directives can and cannot do

`robots.txt` is a voluntary crawl instruction. It MUST NOT be used to protect
private data, hide secrets, guarantee removal from an index or authenticate a
User-Agent. It is publicly readable and can reveal listed paths. For a wholly
private host, a generic `Disallow: /` MAY express intent, but network and
identity controls remain mandatory; do not enumerate sensitive path names just
to "hide" them.

Private or administrative responses that a crawler is allowed to fetch SHOULD
carry:

```http
X-Robots-Tag: noindex, nofollow, noarchive
Cache-Control: private, no-store
```

`noindex` is not data protection. A crawler must fetch a URL to observe this
directive, so blocking the same URL in `robots.txt` can prevent de-indexing.
If a previously public route must disappear from search, use an intentional
removal sequence: remove private content immediately, serve the appropriate
status or crawlable `noindex` response, request removal through supported
search tooling when needed, verify disappearance, and only then tighten crawl
blocking. Authentication is required throughout.

Sitemaps, feeds, canonical links, structured data, OpenAPI descriptions and
machine-facing navigation files MUST contain only intentionally public URLs.
For a private or concealed service, do not publish `llms.txt` or an API catalog.
On a mixed host, generate them exclusively from public records.

### 47.3 Verifying declared bots

A User-Agent is trivial to forge. An edge allow decision SHOULD combine:

1. claimed User-Agent;
2. official IP ranges when the provider publishes them;
3. reverse and forward DNS verification when recommended by the provider;
4. cryptographic bot authentication when available;
5. observed rate profile and behavior.

Verification belongs at the CDN, WAF or reverse proxy. The edge MUST remove any
client-supplied bot-verification header and add its own normalized decision over
a trusted internal hop. The application MUST NOT trust an arbitrary header
from the client.

Unknown automation follows a measured progression:

```text
observe -> rate limit -> managed challenge -> block
        -> canary only after confirmed abuse and approval
```

Prompt injection, data poisoning and hostile instructions embedded in public
content MUST NOT be used as crawler defenses. They can harm legitimate users
and downstream systems and do not enforce network access.

## 48. Resisting Automated Probing

### 48.1 Minimize the externally visible surface

- Expose only the reverse proxy or access gateway; keep application,
  database, cache, metrics, debug and deployment ports private.
- For browser operator services, expose only the canonical login/application
  origin through server-managed Nginx; do not add an operator-IP allow-list.
- Do not embed Nginx in a service image or Compose project. Each service binds
  a loopback upstream and the host Nginx configuration remains the only public
  routing and TLS authority.
- Disable debug mode, directory listing, default virtual hosts, sample routes,
  framework consoles and generated API documentation in production unless they
  are explicitly protected.
- Remove precise server/framework version banners and unnecessary response
  headers. Do not rely on banner removal as the main defense.
- Do not ship repository metadata, environment files, backups, source maps,
  test fixtures, build manifests containing internal paths or default
  credentials in the web root.
- Require an allow-listed `Host`/authority and reject unknown hosts before the
  application. This reduces virtual-host and reset-link poisoning.
- Unknown paths MUST return a real bounded `404`; a single-page application
  fallback MUST NOT return the authenticated shell with `200` for arbitrary
  probe paths.

### 48.2 Normalize and constrain requests

At the edge, normalize the path once and reject ambiguous encodings, traversal,
conflicting length/transfer headers and malformed requests. Allow only required
HTTP methods, content types and protocol features. Bound:

- header count and total bytes;
- URI and query length;
- request and decompressed body bytes;
- multipart member count and size;
- connection, header, body and upstream timeouts;
- concurrent requests and expensive operations;
- websocket/message size and lifetime when applicable.

Rate limits SHOULD combine source network, authenticated identity, route class,
credential and behavioral signals. An IP-only limit is insufficient behind
shared networks and easy to evade with distributed probes. Expensive routes
need smaller independent budgets. Failed authentication, missing routes and
challenge failures require limits even when successful traffic is low.

Use a managed challenge only where browsers are expected and accessibility is
preserved. Machine APIs SHOULD use authenticated quotas, mTLS or signed
requests instead of interactive challenges.

### 48.3 Application protections remain necessary

Edge filtering does not replace:

- authentication and object-level authorization;
- CSRF protection for cookie-authenticated mutations;
- strict CORS allow-lists where cross-origin access is required;
- secure, `HttpOnly`, `SameSite` cookies and bounded sessions;
- input schemas and output encoding;
- content security policy, frame restrictions and MIME sniffing prevention;
- parameterized database access;
- idempotency and replay protection for sensitive operations;
- safe file upload validation and storage outside executable/web roots.

Return uniform errors for unauthorized and invalid resource access when detail
would aid enumeration. Detailed reasons belong in protected, redacted logs
linked by a correlation ID.

## 49. Observability Without New Leakage

Maintain structured edge and application events with at least:

```json
{
  "timestamp": "<UTC time>",
  "requestId": "<opaque id>",
  "routeClass": "<public|authenticated|concealed|unknown>",
  "status": 404,
  "latencyMs": 12,
  "claimedUserAgent": "<bounded family>",
  "verifiedBot": null,
  "automationPurpose": "unknown",
  "policyVersion": "<revision>",
  "decision": "rate_limited"
}
```

Minimize or mask IP data and keep it only under a defined privacy and retention
policy. Bound User-Agent, path, query and header fields; never copy arbitrary
request bodies or credentials into access logs.

Alert on:

- abrupt public reachability or DNS changes;
- a private route appearing in a sitemap, feed or machine-readable catalog;
- bot policy or `robots.txt` change without an approved revision;
- unknown-host traffic and new externally reachable ports;
- bursts of `401`, `403`, `404`, `405`, `413` or `429` responses;
- dictionary traversal of common administration, backup and secret paths;
- unbounded query-parameter crawling or rapidly changing identifiers;
- a claimed trusted bot that fails edge verification;
- repeated challenge failure or distributed low-rate probing;
- artifact/log secret-scanner findings;
- unusual credential issuance, deployment identity use or signing activity.

Alerts MUST identify policy and release revisions and provide bounded evidence,
not raw secrets or full personal data.

## 50. CI And Deployment Verification

### 50.1 CI gates

Automated checks MUST verify:

- workflow permissions are minimum and untrusted jobs receive no protected
  secrets;
- dependencies/actions/images are immutably pinned under policy;
- source and final artifacts pass secret and high-risk-file scans;
- final image layers contain no deleted-but-retained credentials;
- artifact manifest, signature, provenance and digest are consistent;
- private URLs are absent from sitemap, feeds, structured data, API catalogs
  and machine-navigation files;
- security headers and cache directives match route classification;
- unknown paths, methods, hosts, oversized inputs and malformed requests fail
  with bounded responses;
- edge bot decisions match the versioned registry and forged verification
  headers are ignored;
- UI/UX and legitimate public crawler behavior do not regress when edge rules
  change.

### 50.2 Deployment smoke tests

Test from both sides of the boundary:

1. from an unauthorized external network, concealed listeners are unreachable
   and private routes disclose no application content;
2. from an approved identity/network, required routes work;
3. a forged trusted-bot User-Agent and forged verification header receive no
   privilege;
4. public pages remain available only if their policy allows them;
5. administrative and authentication responses use no-store and non-indexing
   directives where applicable;
6. source maps, environment files, repository metadata, backups, diagnostics
   and default documentation routes are unavailable;
7. a release digest and running version match the approved manifest;
8. logs and failure output contain no deployed secret.

Record the vantage point, policy revision, release digest and exact result.
Testing only from inside the target network cannot prove public concealment.

### 50.3 Mandatory Pre-Push Security And Exposure Audit

Every branch or tag push requires a security `PASS` for the complete outgoing
diff. Security is never `N/A`: even a documentation-only or styling-only diff
can disclose a hostname, credential, private route, dependency assumption or
unsafe instruction. The depth of testing is impact-based, but the review and
baseline machine checks are unconditional.

#### 50.3.1 Security Pass Required For Every Push

The pre-push review MUST inventory changes to:

- authentication, authorization, sessions, identities, roles, ownership and
  tenancy boundaries;
- routes, listeners, protocols, external connections, webhooks, callbacks and
  browser or agent-facing endpoints;
- secret creation, input, storage, rotation, revocation, logging, backup,
  artifact and deployment paths;
- parsers, uploads, archives, templates, commands and every other untrusted
  input boundary;
- database/schema migrations, object references, file permissions and
  transaction or concurrency boundaries;
- dependencies, lock files, build images, CI workflows, runner permissions,
  release manifests and deployment definitions;
- security headers, cache policy, rate limits, size/time/count limits, error
  responses, audit events and security documentation.

At minimum, every outgoing revision MUST pass the repository's secret and
high-risk-file scan, dependency and supply-chain policy checks, security-policy
lint and the narrowest relevant security tests. An affected trust boundary also
requires:

1. an updated threat, data-flow or exposure record;
2. authorization tests for allowed and denied identities, including
   cross-tenant/cross-owner cases when applicable;
3. malformed, oversized, replayed, forged and unauthenticated input tests at the
   changed boundary;
4. verification that logs, errors, backups, caches, artifacts and client state
   contain no newly exposed secret or confidential data;
5. verification that limits are enforced at runtime rather than only displayed
   or documented;
6. exact commands, tool versions, inspected paths and results recorded against
   the outgoing revision.

A scanner warning, an unreviewed dependency/security-policy change, a new route
without an exposure classification or an untested authorization branch blocks
the push. A risk acceptance is a material operator decision, not a passing
scan.

#### 50.3.2 Conditional Private And Concealed Exposure Pass

This profile is mandatory on every push when the deployed system contains any
listener, route, page, resource or hostname classified `private` or
`concealed`, or when the stated objective is maximum resistance to discovery by
crawlers, agents and automated probes. A mixed service evaluates this profile
only for its private/concealed surfaces and their shared infrastructure. `N/A`
is permitted only when neither such a surface nor such an objective exists; an
unrelated diff receives a proportionate no-impact `PASS`, not `N/A`.

The outgoing revision MUST prove that:

- the route/listener registry, DNS, reverse-proxy, firewall and private-access
  policies contain no accidental public path to concealed surfaces;
- concealed listeners are absent from the public Internet and private routes
  return no protected application content before authentication;
- private/concealed URLs and identifiers are absent from sitemaps, feeds,
  `llms.txt`, OpenAPI/API catalogs, JSON-LD, canonical/alternate metadata,
  public source HTML, public Documentation articles and client bundles;
- source maps, environment files, repository metadata, backup archives,
  diagnostics, default framework documentation and directory listings are not
  publicly retrievable;
- reachable private responses use the required `noindex`, `nofollow`,
  `noarchive`, no-store and security headers without treating those headers as
  access control;
- a wholly concealed host does not publish a `robots.txt` inventory of private
  paths; obscurity, non-standard ports and hidden navigation are not counted as
  controls;
- ordinary crawlers, claimed known bots, AI agents and forged verification
  headers receive no additional reachability or privilege;
- unknown hosts, paths, methods and malformed probes fail with bounded,
  non-revealing responses.

Verification MUST include an unauthorized external-network vantage point and an
approved internal identity/network. Record DNS and port observations, requested
URLs, response status/headers/body classification, policy revision and running
release digest. Testing only from inside the protected network, or checking only
`robots.txt` and page metadata, cannot produce a concealment `PASS`.

Adding, removing or reclassifying a surface requires a machine-readable
exposure diff. Any transition between `public/indexable`,
`public/non-indexable`, `private` and `concealed` is material and must update the
route/listener registry, edge policy, bot policy, documentation and applicable
SEO/GEO registry in the same outgoing revision.

## 51. Incident Response For Suspected Disclosure

Treat a secret printed to CI output or uploaded into an artifact as disclosed,
even if the log or artifact was quickly deleted. Caches, mirrors, notifications
and job viewers may have copied it.

The response MUST:

1. stop further publication or deployment of affected artifacts;
2. revoke and rotate exposed credentials from a clean trusted environment;
3. invalidate sessions, signatures or releases whose trust depends on them;
4. quarantine affected logs, caches and artifacts without destroying evidence;
5. determine source revision, jobs, readers, duration and downstream use;
6. rebuild from a clean revision and fresh trust material;
7. verify runtime, registry and configuration state;
8. document impact, timeline, containment and prevention;
9. add a regression test or policy check for the leak path.

Deleting the Git commit is not sufficient because clones and caches retain
history. Rotate the secret first, then perform repository-history remediation
under a separately approved plan.

## 52. Definition Of Done

Security and exposure control are complete only when:

- every value is classified and every trust boundary has a distinct identity;
- untrusted CI receives no production secrets or write/deploy permissions;
- runners, dependencies, build contexts, caches and artifacts enforce the
  documented isolation and retention policy;
- release bytes have authenticated provenance and are promoted without
  environment-specific rebuilding;
- deployment injects secrets only at runtime and never prints substituted
  configuration;
- the external exposure mode of every listener and route is documented and
  tested from an unauthorized vantage point;
- crawler and automation decisions come from a versioned Bot Policy Registry;
- `robots.txt`, `noindex` and obscurity are never presented as access control;
- known bots are verified at a trusted edge and unknown automation follows the
  measured escalation path;
- logs and alerts detect leakage and probing without becoming a new data leak;
- incident revocation and clean rebuild have been exercised;
- all material differences have explicit recorded operator confirmation.
