# Public Shared notes

## Approved scope

On 2026-10-05 the operator approved implementing the public note and password
page using the updated central Part 01, section 11, Saturn Shared case study.
This is a private style exception for `/s/<token>` only. Owner Shared, Settings,
Crusher and native Obsidian keep their existing appearance. The operator's
current Mastermind rendering remains available with `?legacy=1` (or
`&legacy=1` alongside other parameters), until the operator requests removal.

## Information and visual contract

Legacy shows a compact dark password gate or a large note title followed by
content. The new gate explains the private link, asks for the sender's password
and offers Continue. The opened page shows Mastermind identity, permission and
expiry in a dark header, then Shared note, the actual title and the note body.
About access and attribution follow the content. Editing is directly in the
document; there is no separate Edit action.

The public light view alone uses a warm background (`#f3f1eb`), paper panel
(`#fffef9`), dark ink (`#171714`), muted text (`#6d6b63`) and quiet separators
(`#d8d4c9`). Space Grotesk regular/bold serves prose and controls; code remains
monospaced. Its accent blends the configured Shell accent with dark ink for
contrast. The reading column is capped at 960px; the password shell at 480px.
Controls are at least 46px high. The gate's subtle shadow and expanded font
roles are explicitly scoped exceptions to the operational interface standard.
Permission and expiry remain visible on narrow screens. Hidden scrollbars do
not disable scrolling. Reduced motion, focus and keyboard navigation apply.

## Access and editing contract

Both presentations use the same capability APIs, password handler and editor.
The switch changes presentation only and persists through unlock. No note
identity, content or expiry is exposed before authorization. Passwords are
cleared after submission; a one-character password remains valid. Rejection,
rate limiting, network failure and unavailable links have distinct feedback.
Healthy service state stays quiet in the new gate.

The server supplies permission, title and link expiry with the authorized note
projection. Filtered references and protected fragments remain protected; no
file previews, resource resolver, owner API access or browser persistence is
added. View only describes editing permission, not impossible-copy protection.

Edits debounce for 900ms and support Ctrl/Cmd+S. ETag/If-Match and projection
identity prevent stale writes. A conflict shows the current version and retains
the unsaved draft for an explicit merge. Typing during a save is saved next;
polling cannot overwrite a dirty document. Tab moves between controls.

## Verification

Verified on 2026-10-05:

- `python -m pytest -q`: **706 passed, 16 skipped** on Windows (121 seconds).
  Skips cover platform/tool-specific checks and the separately run Bridge
  conformance path; they are not Linux acceptance evidence.
- `python scripts/qualify_public_shared.py`: **PASS**, seven reported check
  groups across new and legacy, followed by canonical-file verification.
  It runs actual Core HTTP and Chromium against the same synthetic notes,
  resetting only that fixture between presentations. It covers password `1`,
  rejection and retry, pending/duplicate submission, reading/editing, autosave,
  typing during save and polling, second-browser refresh, ETag conflicts,
  retained drafts, explicit merge, keyboard save, expiry and revocation.
- Matching screenshots cover desktop, 390px mobile, long titles/content,
  locked/opened/view/edit and unavailable states. The 720px viewport verifies
  reflow corresponding to a 1440px window at 200%, not browser-chrome zoom.
  Scroll remains functional without a visible scrollbar. Keyboard focus,
  46px primary controls, reduced motion and text contrast (including white,
  yellow, green, pink, black and blue configured accents) were checked.
- No uncaught browser errors or CSP violations. The API checks exercise both
  variants, restricted assets, pre-unlock privacy, CSRF, reference injection,
  stale writes, expiry and policy invalidation. The authorized `expires_at`
  field does not appear in the unauthenticated policy response.
- Ruff, repository validation (38 documents), exposure inventory (174 routes)
  and changed JavaScript syntax checks pass.

Local screenshots and the structured browser report are in
`artifacts/public-shared/`; CI now repeats this isolated browser qualification
and retains that directory. The run uses offline Runtime coordination and
does not qualify a native Obsidian process or an external service. Rate-limit
and transport-error UI responses are fault-injected; domain rate-limit tests
and real password/edit authorization remain separate checks. No private Vault,
real credentials, live model or provider API is involved. CI has been updated
but no remote run, commit, publication or deployment is claimed here.
