# Crusher: processing contract and local readiness

Current placement is [context-indexing](context-indexing.md). The current
qualification is recorded in [its ledger](CONTEXT_INDEXING_IMPLEMENTATION.md).
The earlier checkpoint below describes the legacy image and direct credential
binding; the new candidate uses scoped Wyvern → Kernel/Volt.

## Historical live Google checkpoint, before context-indexing, 2026-09-19

That local checkpoint used the real Google API with `gemini-3.8-flash` for text
and media. Core starts with `mastermind.api:create_app`; the controlled provider
override is absent. The owner-supplied key is stored as a secret in Volt and
resolved through Kernel's `services.mastermind.secrets.ai_provider_key` binding.
It is not a Compose value, browser value, repository file or report field.

Four bounded scenarios completed all ten states through the actual browser,
Core, Worker, native Vault coordinator and Google:

| Source/check | Result | Placement |
| --- | --- | --- |
| Text file, actual browser picker | PASS, 23 s; source facts and real Markdown line breaks retained | `LOW_CONFIDENCE`, 0.85, safe Inbox |
| Public `example.com` URL, actual source-link form | PASS, 16 s; fetched/extracted public page becomes a note | `MODEL_UNCERTAIN`, 0.30, safe Inbox |
| Synthetic speech WAV, actual drag/drop, approximately 848 KiB | PASS, 33 s; Cedar/three branches/ten key notes/root facts retained | `LOW_CONFIDENCE`, 0.85, safe Inbox |
| Unambiguous knowledge architecture source | PASS, 21 s; root → main → key, verified branch link and canonical digest | `Integration/Integration key.md`, 0.95 |

Only the pre-existing synthetic integration hierarchy was used for context;
the probe checks its exact bytes before submitting. Created test notes were
verified and removed individually using their current digest. Copies of their
synthetic outputs and structured evidence remain in
`artifacts/live-ai-20260919/`. The entire Vault was not transmitted.

Google's GET for the already-deleted test media identity returned 403. Deletion
was therefore verified against a successful complete Files listing (200 and
the test identity absent), rather than inferred from that GET status.
Core returned to `HEALTHY`, semantic indexing to `READY`, and Neptune remained
linked. A scan of repository/artifact files and six relevant containers' logs
and environment found no copy of the supplied credential. On the owner's
follow-up cleanup request, the original plaintext input file was deleted;
349 repository/artifact files were checked without finding another copy.
The operational secret remains in Volt so the live pipeline stays connected.

Live testing exposed a compatibility defect: Google adds `thoughtSignature`
alongside final text, while the old direct adapter discarded such text parts.
The deployed adapter now accepts that metadata without persisting it or treating
it as prose. Google describes this response metadata in its
[thought signatures documentation](https://ai.google.dev/gemini-api/docs/generate-content/thought-signatures).
Four offline regression tests cover signed/plain parts, thought
exclusion, schema/finish/budget failures and a retryable quota response. One early
generation also double-encoded line breaks; the prompt now explicitly requests
actual newlines, and the live probe checks the generated Markdown.

This qualifies the **currently deployed direct Google adapter**, not the
in-progress Wyvern source migration. Its local image is
`mastermind-core:live-google-tested`; the parser repair is reproduced by
`scripts/integration/patch_legacy_google.py` against the exact legacy image's
`gemini.py`. Do not replace the current source with that legacy file. Wyvern's
Google driver already consumes signed text; its service-to-service deployment
still needs a separate live qualification. The Markdown prompt clarification is
also present in the current Mastermind source.

The tests establish the listed small-source paths, not production-scale quality,
every media format, account billing totals or live retry/recovery behavior.
Quota and malformed-response regressions use isolated synthetic responses.

## Earlier controlled-provider verification (historical)

The local service at `http://localhost:18390` is healthy. A fresh bounded text
submission completed every stage and committed one real note through the native
Vault coordinator. The probe verified its job marker and digest, then deleted
only that disposable note. Evidence:
`artifacts/shared-ui-20260919/crusher-readiness.json`.

The public UI follow-up additionally verified a real browser file selection,
incremental digest, upload/acceptance and all ten pipeline states through the
redesigned link/drop interface. Its one generated test note was checked and
removed. Evidence: `artifacts/public-editing-20260919/crusher-readiness.json`.

Before the live qualification above, Google's live API was not connected. Core started with
`core_fixture:create_app` from the explicit
`scripts/integration/crusher-fixture.compose.yml` override. It installs an
`httpx.MockTransport` for Google requests. The current identifiers are
`integration-text-model` and `integration-video-model`; the credential is
synthetic. Real Core, Worker, Obsidian and storage run around the fixture.
The fixture generates a predefined note, so a successful local job does not
demonstrate useful AI output, Google quota, real model availability or quality.

## Acceptance and permissions

File hashing runs in a dedicated browser module worker. Its own CSP permits
same-origin module imports while keeping other resources denied. The public
worker script needs this policy separately from the Shell page; a deny-all
worker policy caused `File hashing failed.` in Firefox before upload. The repair
is qualified with `node scripts/probe_file_hashing.cjs` in Chromium and Firefox,
plus `probe_crusher_readiness.cjs --file-ui --firefox` and the same command with
`--drop` for actual upload/processing on the explicit local provider fixture.
Install the pinned browser builds with
`node node_modules/playwright/cli.js install chromium firefox` before these checks.

The owner and unlocked visitor UI accept one source link per line or a file
selection/drop, up to twenty entries per batch. There is no source-type selector.
YouTube hosts are recognized as video sources; `.git` URLs and repository-root
URLs on GitHub/GitLab/Bitbucket are recognized as Git; other HTTP(S) links are
web sources. The API continues to support text and explicitly authorized Saturn
resources. A visitor exchanges a six-digit one-use
Dashboard code for a 30-minute submission session. The code also expires after
30 minutes. Visitors cannot browse Vault or select private Saturn files.

Text is limited to 1 MiB; uploaded files to 2 GiB. Browser hashing runs
incrementally in a worker. Core verifies the upload digest before accepting it.
Acceptance uses an idempotency key, reserves processing capacity and persists a
job. A repeated accepted request cannot create a duplicate note. Visitor status
receipts live for 24 hours and reveal only their accepted jobs; the browser keeps
credentials and receipts in memory.

The locked public page has a centered code gate and separate reachability box.
The unlocked page shows `mastermind crusher`, the remaining session time, source
links and a large file drop area. A file drag anywhere on the unlocked page
activates a dimmed fullscreen overlay with a dashed accent border. Shell and
public Crusher use the configured Mastermind accent; green/red retain their
semantic reachability/notification roles. Expiry disables new submission while
accepted job receipts remain usable. The page never displays generated notes.

The unlocked page uses two equal columns: search/history on the left and source
input/drop on the right, without a separate Submissions heading. The layout
tracks available content width, including the fixed sidebar. At 820px or less
of available workspace width, the input panel precedes history in one column.
Visual scrollbars are hidden without disabling page or field scrolling.

## Sources and isolation

Supported sources include text, bounded uploads, public web pages, YouTube/video/audio and supported documents/archives, Git repositories and owner-only Saturn resources read through Neptune. PDF/OCR, DOC via antiword, DOCX, RTF, XLSX cached values, PPTX and EPUB extraction runs in the dedicated Worker. Spreadsheet formulas and Git hooks/scripts are never evaluated. Git helpers and arbitrary commands are not accepted from a source.

Worker receives only the current source and bounded chunks. It has no Vault mount, database, provider/agent credentials belonging to other principals or commit API. Extractors run through the Linux sandbox and allowlisted binaries; browser requests and redirects undergo public-address checks. The offline multilingual E5 model is pinned by digest, uses at most 512 tokens/chunk and never downloads model artifacts at runtime.

The Worker browser is the separately pinned official stable Chrome for Testing **153.0.8010.36**, recorded with download URL and SHA-256 in `worker-browser.lock.json`. The build verifies and installs those bytes and uses Playwright only as the controller. It does not install the older browser bundled with Playwright. The executable still enters the same Landlock/seccomp wrapper; all network requests pass through the bounded parent broker. Full image CI checks the actual browser version, executes a JavaScript-generated article and rejects its attempted request to loopback. The initial switch addresses the vulnerable Chromium 151 baseline; only a fresh scan of the resulting exact image can establish its new vulnerability status.

## Processing stages

| Stage | Display | Work |
| --- | --- | --- |
| QUEUED | 0% | Persist the accepted source and wait for the single active pipeline. |
| ACQUIRING | 5% | Transfer a verified local upload/text to Worker, fetch a public URL, clone a bounded Git source, or read the selected Saturn resource through Neptune. A YouTube URL is passed to the media adapter. |
| NORMALIZING | 15% | Persist an acquisition-verification checkpoint. This is currently a marker; it is not a separate transformation or model call. Worker extraction performs the actual normalization. |
| EXTRACTING | 20% | Isolated Worker extracts bounded text or prepares media. A browser renderer is used when the extractor requests it. Network acquisition rejects private network targets and unsafe redirects/helpers. |
| UNDERSTANDING | 40% | Gemini returns structured title, summary, topics, entities and suggested links. Text is token-counted and bounded before submission; media uses the separate media-model adapter. No full Vault context is included here. |
| PLACING | 55% | Run local context-indexing, then apply Crusher-only structural eligibility and calibrated fallback. |
| GENERATING | 65% | The selected Wyvern Adapter returns typed title, summary and body for the frozen template. It does not choose arbitrary filesystem paths or execute tools. |
| VALIDATING | 85% | Check the result schema, output size, secret patterns and forbidden HTML, embeds, links and reference syntax. Invalid output fails; it is not saved as a note. |
| COMMITTING | 95% | Revalidate hierarchy, allocate a unique basename and commit through the canonical coordinator/journal. Add the verified branch reference and provenance footer. |
| COMPLETED | 100% | The durable note exists in Vault. The Crusher response remains progress-only. |

Percentages are fixed milestones, not a measurement of time remaining. The
Crusher page deliberately shows no generated prose or result note path. The
owner views the resulting note in Vault.

## Destination and privacy

The hierarchy starts at the configured root (default `root.md`). Its links to
`#main` notes define the first branches; links from `#main`/`#key` notes to
`#key` notes define deeper branches. Merely placing a tag on an unrelated note
does not connect it to this hierarchy.

Context-indexing searches ordinary notes as well as structural branches, combines
local retrieval channels, reranks expanded evidence and checks consistency.
Crusher alone restricts allowed anchors to the unique root/main/key structure.
Insufficient or contradictory evidence uses the configured pool.

Every resulting file is stored in `root/crusher`, independently of graph placement.
The new note links to its selected anchor or `root/pool.md`; it does not rewrite
that parent. The configured static template (default
`root/templates/example crusher.md`) is snapshotted at acceptance. The combined
Settings → Obsidian & search card controls pool, template and local Curator.

No retrieved note excerpts or branch profiles are transmitted externally for
placement. Source understanding and generation still use a selected external
Wyvern Adapter, with bounded source/understanding/template packets. The provider
credential belongs to Wyvern through Kernel/Volt. See [context-indexing](context-indexing.md)
for budgets, calibration, configuration recovery and migration boundaries.

## Operational bounds

Default bounds: 1 MiB raw text, 2 GiB source, two concurrent source uploads, 16 GiB incoming/work quota, one active job, queue 100 globally / 20 per public session. Source archive expansion is at most 8 GiB, 10,000 members and depth 16. Fetch/clone is bounded to 15 minutes, extraction to 20 minutes, a provider attempt to 5 minutes and the accepted job to 60 minutes. Successful temporary data are removed promptly; failed sources expire within 24 hours.

Expiry of a submission session does not cancel already accepted work.

## Failure and recovery

One pipeline executes at a time. Each accepted job has a 60-minute deadline.
Steps persist checkpoints, attempts and leases. Retryable failures have at most
three attempts, with normal backoffs of 5 and 30 seconds; a bounded
`Retry-After` can increase these delays. Non-retryable validation failures end
the job. A restart resumes durable work without duplicating the canonical
commit. An uncertain provider response can require a repeated billable call
after switching to a live API; commit idempotency does not guarantee exactly
one remote inference. Temporary media/provider files have cleanup paths.

## Operating the local live profile

Restart/recreate only the existing tested Core image with the local override:

```powershell
docker compose -f compose.development.yml -f .local/integration/core-override.yml -f .local/integration/live-google.compose.yml up -d --no-build --no-deps core
docker compose -f .local/integration/compose.yml up -d --no-build --no-deps --force-recreate neptune
```

Do not add `crusher-fixture.compose.yml` to that command. The live override
contains no credentials. Rebuilding the workspace would select the in-progress
Wyvern implementation and is not equivalent to restarting this qualified image.

`node scripts/probe_crusher_live.cjs --live --file` spends real provider quota;
`--web`, `--audio` and `--placement` select the other bounded scenarios. The audio
scenario expects the local synthetic `artifacts/live-ai-20260919/source.wav`.
The probe refuses a fixture entrypoint or any unexpected hierarchy content,
never loads a provider key, checks final readiness after asynchronous indexing,
and deletes only its own committed note. Ordinary CI must not invoke this probe
with live credentials. The existing `probe_crusher_readiness.cjs` remains
restricted to the controlled provider.

## Provisioning another direct-provider stand

1. In `sudo updater tui`, connect Wyvern to Kernel and create a Google Adapter
   with its API key, actual model profiles and required capabilities. The
   credential is stored in Volt; Mastermind does not resolve it.
2. Grant the Mastermind client access to that Adapter. In Settings → Wyvern,
   connect the client and select the `text` and `media` function bindings.
   Legacy `ai_provider_key` and `mastermind.crusher.*_model` bindings are unused.
3. Start Core with its normal production factory, omitting the explicit
   `crusher-fixture.compose.yml` override. In this local topology, recreate
   Neptune when Core's network namespace changes.
4. Run a small non-sensitive text submission and a representative media case;
   verify provider responses, schema compatibility, factual quality, placement,
   billing/quota and cleanup. Only then claim live-provider readiness.

These steps now have bounded live evidence for the local direct-provider image
described above. They do not configure the separate Wyvern gateway migration.
