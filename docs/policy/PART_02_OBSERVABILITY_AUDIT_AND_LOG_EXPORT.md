# Part 02. Observability, Audit And Log Export

> This is a normative component of the [Part 00 documentation authority](./PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md).

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT** and **MAY** are
normative. Numeric defaults may change only after workload measurement, while
the safety property behind every limit MUST be preserved.

## Central Authority And Material Divergence

This Part takes precedence over conflicting project-local documentation.
Project documents MUST adapt these rules to current project-specific values
without weakening them. A material implementation difference follows the
reporting and decision protocol in [Part 00](./PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md#1-mandatory-material-divergence-protocol); stale local documentation is corrected and is not an alternative authority.

---
## 10. Logging Model

Application logs, security audit events and process-manager output have
different purposes and MUST be bounded independently.

| Stream | Purpose | Preferred storage |
| --- | --- | --- |
| Operational log | Debug runtime behavior and integrations | Rotated JSONL or process manager |
| Audit event | Explain who changed protected state and with what result | Transactional database with retention |
| Error record | Preserve high-value diagnostics for failures | Derived export plus structured source event |
| Update job event | Explain a privileged local mutation and rollback | Atomic job state plus bounded journal |

Do not treat container stdout as the only audit trail. Do not duplicate every
debug message into the database.

### 10.1 Structured Event Contract

Every audit event SHOULD contain:

- unique event ID;
- occurrence time in UTC;
- severity and outcome such as success, error or denied;
- stable action name;
- actor type and non-secret actor identifier;
- target type and stable target identifier;
- concise human-readable summary;
- request or correlation ID;
- transport method when relevant;
- bounded structured context;
- an optional structured error object.

The error object preserves recorded facts:

```json
{
  "type": "ValidationError",
  "code": "INVALID_INPUT",
  "message": "A concise original message",
  "cause": null,
  "stack_trace": null
}
```

Unknown fields remain `null`; the system MUST NOT invent a stack trace or
cause. Large bodies and binary payloads do not belong in the event.

### 10.2 Secret Redaction

Redaction is a central serialization step, not a convention left to every
caller. It MUST recursively inspect object keys and known credential patterns
before data reaches any sink.

Never log:

- passwords or password reset values;
- bearer, API, enrollment or one-time tokens;
- cookies or session material;
- private keys or decrypted identity material;
- complete connection strings containing credentials;
- full request or response bodies from authentication and provisioning paths;
- the contents of `.env` files.

Masking only `key=value` text is insufficient because secrets also appear in
JSON, headers, URLs and nested exceptions. Truncation is not redaction: a
truncated secret is still a secret.

## 11. Retention, Disk Limits And RAM Limits

### 11.1 Unified Baseline Limits

The following values are a practical starting profile derived from the
reference implementations. The strictest applicable limit always wins.

| Layer | Count limit | Age limit | Byte limit |
| --- | ---: | ---: | ---: |
| Audit database | 10,000 events | 30 days | 64 MiB estimated retained payload |
| One JSONL file | configurable line cap | 30 days | 5 MiB |
| Complete application log directory | all files combined | 30 days | 64 MiB |
| Ordinary container stream | 3 rotated files | implementation-managed | 10 MiB per file |
| Chatty auxiliary container | 2 rotated files | implementation-managed | 5 MiB per file |
| Web event list | 200 initially | retained window | response bounded to 1,000 |
| Service-manager burst control | 200 messages | 30 seconds | host policy still required |

These values are not universal constants. A production sizing review SHOULD
calculate:

```text
daily_bytes = average_event_bytes x events_per_second x 86,400
retained_bytes = daily_bytes x retention_days x safety_factor
```

The safety factor covers bursts, indexes, metadata and compression variance.
The chosen directory budget MUST be a small, explicit fraction of the target
filesystem, and free-space monitoring must alert before the budget is reached.

### 11.2 Trimming Order

Database audit retention runs after append or in a frequent maintenance job:

1. Delete events older than the retention cutoff.
2. Keep only the newest configured event count.
3. Delete oldest events whose cumulative estimated size exceeds the byte
   budget.

File retention runs in this order:

1. Rotate the active file before it exceeds its per-file limit.
2. Remove expired rotated files.
3. Enforce the directory byte budget oldest-first.
4. Prefer deleting derived or resource-specific logs before the aggregate audit
   stream when policy permits.

Database file size may remain physically allocated after rows are removed, but
the space must be reusable and logical growth must stop at the configured
budget.

### 11.3 RAM-Safe Processing

Bounded disk usage does not automatically mean bounded memory usage. Reading a
64 MiB log set, parsing it into objects, serializing it again and building a ZIP
can require several times 64 MiB at peak.

Required rules:

- Append asynchronously or through a bounded queue; do not perform synchronous
  file writes on a UI or event-loop thread.
- Use a rotating writer. Do not read and split the complete active file after
  every append.
- Tail files by seeking from the end or maintaining an index. Do not load the
  complete file to display the last records.
- Paginate database audit queries. Do not materialize the entire retention
  window for a normal web response.
- Generate large exports as a stream or through a restricted temporary/spooled
  file. Avoid an in-memory ZIP buffer and multiple full JSON copies.
- Avoid embedding large log or backup binaries as base64 inside JSON. Base64
  adds roughly one third to the payload and commonly creates decoded, encoded
  and request-body copies in RAM.
- Put a maximum size on one event and one error context. Oversized diagnostic
  fields are summarized with a visible truncation marker.
- Bound log queues and define overflow behavior. Dropping low-severity debug
  entries with a counter is safer than allowing unbounded RAM growth.

An append-only file without rotation, even if every line is truncated, is a
release-blocking defect. A service-manager rate limit controls bursts but does
not replace total journal retention configuration.

## 12. Web Log View And Download Contract

### 12.1 Compact Web Stream

The Settings log view is intentionally compact, updates in real time and never
renders full stack traces or large JSON payloads. Its visual contract is defined
by Part 01 section 5.5 and the linked `example settings logs` template.

- The internal stream is at most `460px` high.
- A desktop row shows outcome, action, target, actor and local timestamp.
- Success uses semantic green; error and denied use semantic red; text always
  names the outcome.
- Timestamp format is `dd.mm.yyyy hh:mm:ss` in the operator's locale.
- Long values are summarized without changing column geometry.
- Secondary columns disappear progressively on narrow layouts.
- The view requests a bounded page and offers explicit pagination or load-more
  behavior.
- Live delivery appends only records newer than the current cursor, preserves
  server order and deduplicates reconnect overlap by stable event ID.
- When the page is hidden or transport disconnects, the client pauses active
  rendering and resumes from the last cursor or requests a fresh bounded page.
  It MUST NOT buffer an unbounded hidden-page backlog or duplicate rows.
- The browser keeps only a bounded visible window plus explicit older-page
  navigation; server retention MUST NOT be mirrored into an unbounded DOM.

The retention description states every active count, age, per-file and total
byte limit in one place.

### 12.2 Download Authorization And Delivery

Log download MUST:

1. Require an authenticated operator with explicit permission.
2. Create an audit event for the export itself without recursively including
   the not-yet-finished download event in an ambiguous way.
3. Use same-origin delivery and keep the Settings view open.
4. Send `Cache-Control: no-store, private`.
5. Use a timestamped filename such as
   `<service>-logs-<UTC-timestamp>.zip`.
6. Stream the archive or serve a securely spooled file.
7. Remove the spool file after delivery or after a short bounded lifetime.

If export size can be estimated, show it before starting. The endpoint MUST
enforce compressed and uncompressed budgets, a maximum file count and a
maximum duration.

### 12.3 Archive Layout

```text
manifest.json
events.jsonl
errors.json
README.txt
raw/
  <rotated-log-files>.jsonl
```

`manifest.json` contains format and schema versions, service role, creation
time, event and error counts, active retention limits, stored byte estimate and
descriptions of every member.

`events.jsonl` is the complete retained structured event stream within policy.
`raw/` is optional and contains only sanitized, retained operational files.
`README.txt` explains timestamps, redaction, retention and how to correlate an
error.

`errors.json` is a separate, expanded diagnostic document. Each entry contains:

- event ID and occurrence time;
- actor, action and target;
- summary and original recorded message;
- error type and code;
- recorded cause and stack trace;
- request or correlation ID;
- transport method;
- bounded structured context.

Error selection SHOULD use severity/outcome and the structured error object.
Keyword matching may be a legacy fallback, but it is unreliable and MUST NOT be
the primary classifier.

### 12.4 Findings From The Reference Implementations

Reusable strengths already demonstrated include multi-axis database retention,
directory and per-file budgets, rotated container logs, authenticated export,
manifested archives and a separate detailed error file.

The following observed patterns are limitations to remove during unification:

- some components cap event age and count but not retained bytes;
- some host and desktop logs append forever without rotation;
- one desktop path uses synchronous writes on its main process;
- some file trimming and tail endpoints read the complete file into RAM;
- several downloads collect all rows, JSON strings and the complete ZIP in
  memory;
- one classifier infers errors from words instead of a structured outcome;
- redaction varies by caller or masks only a narrow text form;
- journal burst limiting is present without an application-owned total disk
  guarantee.

These are documented boundaries, not recommended architecture.
