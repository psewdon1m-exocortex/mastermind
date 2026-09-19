# Context-indexing implementation ledger

Date: 2026-09-19. Contract: [approved specification](../mastermind_retrieval_curator_pipeline_final.md).
Operation/API: [context-indexing](context-indexing.md).
This records local implementation and qualification, not a production release
or remote CI run. Existing independent Bridge and Wyvern work is preserved.

## Checkpoints

| Checkpoint | Result | Exit evidence |
| --- | --- | --- |
| CP0 baseline and contracts | PASS | Existing 51-test baseline; grouped corpus; real legacy baseline; pinned CPU model/runner preflight |
| CP1 common retrieval | PASS | Independent scoped channels, RRF, rerank, expansion/union rerank, consistency and provenance; ordinary notes searchable |
| CP2 profiles and placement policy | PASS within measured operating point | Incoming-member profiles, unique structural eligibility, separate pool policy, frozen thresholds/model digest guard; quality limits below |
| CP3 template and combined Settings | PASS | Immutable templates, static renderer, LF/CRLF validation, atomic revision/idempotency; actual browser wide/mobile/conflict/picker |
| CP4 local Curator | PASS functional; off by default | Actual Windows/Linux CPU inference, second retrieval and replay with one inference; timeout/invalid scope tests; quality benefit unproven |
| CP5 commit and recovery | PASS | Fixed output folder, outgoing links, waiting/resume, rename/rebind, source cleanup, crash boundaries, encrypted restore/schema-2 barrier |
| CP6 end-to-end qualification | PASS with measurement limits | Linux regression, actual Worker/Wyvern/Kernel/Volt/Google, native Obsidian, owner/guest denial, 8,000-note performance, resource/secret checks |
| CP7 local activation | PASS | Final images healthy on loopback 18390; owner/guest/native passed; restart preserves config/template, 91/91 notes indexed, completed jobs not replayed, actual Neptune/Saturn listing; receipt: artifacts/context-indexing-activation.json |

Entry requirements and outputs are specified in §17 of the approved contract.
Artifacts below are local and ignored by Git. They contain synthetic source
material and sanitized diagnostics, never provider credentials.

## Regression and browser evidence

- Initial Windows broad regression: 551 passed, 16 platform skips, excluding
  the separate large-backup fixture (context-indexing-regression.xml).
- Final broad Linux run: **571 passed, no skips**, 109.97 seconds, non-root,
  read-only, network-disabled Worker, 2 CPU / 2 GiB. Includes the approximately
  356 MiB encrypted backup fixture (context-indexing-linux-final.xml).
- After final source-exclusion and LF/CRLF guards: **104 Linux tests passed**,
  18.30 seconds (context-indexing-linux-delta.xml); 66 targeted Windows tests
  passed. Idle trace-expiry maintenance was subsequently added and checked by
  31 context-indexing tests. Unrelated broad tests were not repeated without a relevant change.
- Ruff, JavaScript syntax, repository validation and 145-route exposure inventory
  passed. Source export secret scan had no findings in 379 files / 4.79 MB at its
  checkpoint (context-indexing-secrets.json); final scan also passed on 380 files /
  4.81 MB (context-indexing-secrets-final.json).
- probe_context_indexing.cjs passed against the isolated real API: combined card,
  readonly output, path picker, draft preservation, validation, simultaneous
  revision conflict/rebase, 390px width and no browser exceptions
  (context-indexing-ui/report.json and wide/narrow screenshots).
- probe_context_live.cjs --live passed on the actual stand: owner file upload
  → eligible branch in **13.469s**; guest upload → pool in **10.317s**.
  Progress-only receipts, private API denial, template, outgoing canonical edge,
  native Obsidian open and native graph were checked. Parent digests stayed
  unchanged. Both synthetic notes were removed using their exact current hashes.
  Evidence: context-indexing-native/report.json and native screenshots.
- The isolated real-provider probe exercised Worker extraction and Google
  generation through **Wyvern → Kernel/Volt**: branch/pool in 8.122s / 8.803s,
  graph-canary exclusion from provider packets, acceptance idempotency, frozen
  template and terminal cleanup (context-indexing-live.json). Its coordinator
  is offline; native qualification is explicitly the preceding probe.

## Quality, failures and provenance

The corpus contains 500 authored cases, grouped by domain/paraphrase family;
source text differs from fixture notes. They are not a sample of the owner's
entire Vault. Thresholds were frozen before opening the accepted 100-case
Physics/History held-out split. Model/corpus/report hashes are in the packaged
context_indexing/calibration.json.

| Variant on final 100-case regression | Automatic | Correct / automatic | Must-pool placed | Coverage |
| --- | ---: | ---: | ---: | ---: |
| Complete, Curator off | 80 | 80 / 80 | 0 | 80% |
| Vector unavailable, separately calibrated | 62 | 62 / 62 | 0 | 62% |
| No profiles ablation | 80 | 80 / 80 | 0 | 80% |
| No expansion ablation | 80 | 80 / 80 | 0 | 80% |
| Curator requested | 80 | 80 / 80 | 0 | 80% |

Complete candidate recall@200 and top-1/top-3 on answerable cases are 1.0.
Descriptive 95% Wilson interval for 80/80 is [0.9542, 1.0]; correlated authored
paraphrases do not provide an independent-sample population guarantee.

The real legacy Hierarchy.place using Gemini 3.8 Flash was measured on a
predeclared 30-case matched subset: both versions placed 10/30 with 10/10 correct
and no must-pool errors. This comparison was made after freezing calibration,
not over all 500 cases. Paid requests used only synthetic data.

Evaluation history is retained:

1. The initial 300-case corpus passed a safety point but failed matched legacy
   coverage: legacy 10, new 0. Semantic weighting and specific-descendant
   preference changed; those held-out domains became development data.
2. Fresh Chemistry/Linguistics domains in the 400-case corpus failed:
   85 automatic / 92.94% precision, six must-pool errors. Independent paragraph
   contradictions required explicit checks. Those domains became development data.
3. The new Physics/History split in the 500-case corpus passed default mode:
   80/80, no must-pool errors. Initial Curator mode failed: 82 automatic / 97.56%,
   two must-pool errors. A guard prevents reinterpretation of strong
   counterevidence; subsequent use of these cases is regression.
4. Actual native-stack testing exposed a source explicitly unrelated to knowledge
   architecture while its candidate had the technical name “Integration key”.
   The additional conservative topic-exclusion guard uses pool without requiring
   a name match. Ranking and frozen thresholds did not change. It adds rejection,
   so legitimate topic contrasts can reduce coverage. The final replay above is
   regression, not new unseen evidence.

Accepted artifacts: context-indexing-thresholds-acceptance.json,
context-indexing-held-out-acceptance.json,
context-indexing-legacy-baseline-acceptance.json,
context-indexing-curator-regression.json,
context-indexing-final-guard-regression.json.
The native counterexample receipt remains in
context-indexing-native/initial-counterevidence-failure.json.

The final Curator-on quality corpus invokes **zero** refinements: positives are
sufficient; negatives are blocked. There is **no demonstrated placement benefit**.
Actual model refinement, second retrieval and durable replay are separately
qualified with an explicitly forced ambiguous assessment. No quality claim
follows from that protocol test. Curator stays off by default; new tuning or
claims of better quality require fresh held-out domains.

## Resource and scale evidence

context-indexing-resources.json: actual offline E5/Curator, three cycles of
16 × 512-token embedding requests plus eight-card Curator input, 2 CPU / 2 GiB.
Peak cgroup memory **1,984,663,552 bytes**, no memory-limit hits or OOM, 36.743s.
Embedding microbatches of two and serialized heavy Worker operations are required.

context-indexing-scale.json: **8,000 synthetic notes**, 20,716,394 source bytes,
approximately 63 MB SQLite and mixed wiki/@ links. Completed-index query times
**4,447 / 4,104 / 3,800 ms**; process peak RSS **951,590,912 bytes**.
Initial creation plus canonical indexing took **143.319 seconds**, distinct
from warm queries. Repeated real E5 vectors measure scan/resource performance,
not relevance quality. Actual offline Curator performed refinement and second
retrieval; two pipeline runs used only one inference through durable replay.

Quality-corpus timings (complete p50 77.5ms / p95 646ms) use a warm reusable
embedding cache and small graphs; they are not cold production SLAs.
No eight-hour soak, 8 GiB transfer, external-disk development or full private
Vault transmission was performed.

## Acceptance matrix

| Cases | Verified boundary and evidence |
| --- | --- |
| T01–T04 | Ordinary-note scope, independent vectors, expansion rerank and dedup: context-indexing/semantic/Curator tests, quality probes |
| T05–T06 | Incoming members, scoped profile isolation, cycles/multiple parents/unreachable/conflicting roles: context tests |
| T07–T10 | Branch/pool fixed folder, missing pool/resume, static template/config snapshots: context/Crusher tests and actual live jobs |
| T11 | Wide/narrow combined Settings, native keyboard controls, conflict/preserved draft: browser Settings probe |
| T12–T13 | Real CPU assist, one second pass; unavailable/timeout/crash reservation, strict handles/no widening: Curator/resource/scale checks |
| T14–T16 | Partial/rebuilding/model mismatch, stale evidence/recompute, unique names/commit crashes: semantic/context/Crusher/storage suites |
| T17 | Actual native note/graph screenshots and outgoing canonical edge; unchanged parent digests: native live probe |
| T18 | Owner/CSRF negatives, scoped profile privacy and actual guest denied notes/settings: API tests and native live probe |
| T19 | Real Core/Worker/Runtime/Bridge and Wyvern/Kernel/Volt/Google calls: isolated + native probes |
| T20–T21 | Repeated bootstrap, preserved template, schema/update rollback, encrypted restore: context/update/backup tests |
| T22 | Frozen calibration, fresh-domain failures/revisions, real-provider matched baseline, final regression: metrics/history above; Curator benefit unproven |
| T23 | Bounded allowlisted traces, terminal cleanup, private-graph canary, source secret scan: tests/live/scan |
| T24 | Candidate/token/iteration/deadline bounds and degradation; actual 2 GiB models and 8,000-note workload: resources/scale/Curator tests |

## Local operations

Before migration, an encrypted backup of the current 368 MB Vault was staged:
operation 4185ebfe59ea4d39524fdd2c37d489a9,
SHA-256 e80e37814dc7e25b30501fa8504be67f5de18b91a6e0650fd2666e175dc2dfcb.
Normal owner-export retention is 24h. Schema 2 rejects older Core; use managed
rollback/restore, never attach a schema-1-only image directly to migrated state.

Core/Worker tags: mastermind-core:context-indexing and
mastermind-worker:context-indexing. Existing Runtime and its native UI remain.
The qualified local Wyvern/Kernel/Volt fixture uses a separate Compose project,
mastermind-context-indexing. Provider material is encrypted Volt state. Core
mounts only a scoped client link and UDS.

Recreate from the service directory:

~~~powershell
docker compose -p mastermind-development -f compose.development.yml -f .local/integration/core-override.yml -f .local/integration/live-google.compose.yml -f .local/context-indexing-stack/mastermind.compose.yml up -d --no-deps core worker
docker compose -f .local/integration/compose.yml up -d --no-deps --force-recreate neptune
~~~

The local override and credentials are ignored. The gateway preparation script
is for isolated local qualification, not production onboarding. Production uses
the shared Updater's Wyvern enrollment and approved release lifecycle.
The Neptune fixture shares Core's network namespace to emulate a host agent;
after Core recreation/restart it must be recreated to reattach. This is specific
to the local fixture. The final activation probe also checks actual Saturn
resource listing through Neptune, beyond healthy-container checks.
Its first five entries were folders, so this receipt does not claim a file-content
download. Curator model readiness is true while its configuration remains off.
Core restart requires owner reauthentication; the Access Key itself is unchanged.

Temporary UI/Worker containers are stopped. Automatic approval review rejected
removal of those containers, their test volumes and source-scan directories
(`blocked by policy`); no alternate deletion was attempted. These local test
artifacts remain on the primary disk. Active service containers and the linked
local Wyvern/Kernel/Volt fixture remain running. The final machine-readable
receipt is `artifacts/context-indexing-completion.json`.
