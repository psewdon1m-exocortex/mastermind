# Weaver retrieval and evidence — 2026-10-06

This document specifies the implemented extension to [Weaver](WEAVER.md). It
preserves the Core/Worker boundary and existing typed consumer contracts. It adds
no public search endpoint, provider calls, answer generation or Crusher authoring
logic. The deployed service must be rebuilt to run these source changes.

## Task-specific selection

`weaver/relevance.py` versions the acceptance policy as `weaver.relevance.v1`.
Lookup and Similar retain shared candidate discovery and content preparation,
but use separate ranking weights and acceptance rules. Placement continues to
use its independently calibrated `crusher.placement.v1` policy.

- Lookup accepts explicit names/declared aliases, topical overlap and verified
  semantic evidence. A verified bilingual candidate below the strong semantic
  threshold can survive as `tentative` if it is sufficiently distinct from the
  scoped background and close to the best candidate. Its explanation explicitly
  states limited confirmation. This repairs the yeast/bread regression without
  changing canonical notes or adding exceptions for particular note roles.
- Similar requires stronger semantic confirmation, or corroborated topical
  evidence. It uses a single retrieval pass, no planning and no Bibliotekar.
  Lexical evidence remains usable when local inference is unavailable, with
  degraded status. Its compact list remains capped at eight notes.
- A scope with fewer than three scored candidates cannot provide an unrelated
  background estimate. Lookup may return an absolutely strong match as tentative;
  Similar requires a higher absolute score. Missing background is reported as
  `null`, not a fabricated baseline.
- Scores are ranking signals, never calibrated probabilities. Passage verification
  still uses E5, not a separate cross-encoder. The thresholds do not eliminate all
  semantic false matches; the measurements below document that limitation.

Exact alias matching uses authorized metadata. Directory depth, `root`, `pool`
and template roles do not grant or remove retrieval eligibility. Crusher's
structural constraints apply only to its placement policy.

## Common evidence packet

Lookup, Similar/Bridge, Walk and placement plans expose **`evidence_packet`** with
schema **`weaver.evidence.v1`**. Existing result fields are retained, including
Placement's legacy `evidence` revision map and Similar's five-field compact items.

| Field | Meaning |
| --- | --- |
| `task`, `snapshot_id` | Operation and authorized graph snapshot |
| `identity_semantics` | `path_bound`; the Vault has no immutable note UUID |
| `score_semantics` | `ranking_not_probability` |
| `completeness` | `complete` or `partial`, reason codes, vector readiness and freshness |
| `sources[]` | `id` (`note:` + path), path, SHA-256 revision, title, score, acceptance, reason, discovery channels |
| `sources[].fragments[]` | Matched/context text, heading, coordinates, source section and optional chunk ID |
| `sources[].graph_paths`, `graph_edges` | Versioned participating notes and actual directed edges |
| `sources[].graph_context_sources` | Versioned linked-note context; distinct from document paragraph expansion |
| `sources[].profile_sources` | Versioned members supporting a placement branch profile |
| `sources[].query_parts` | IDs of original/planned query directions supported by this source |
| `context` | Mode, UTF-8 byte budget, bytes returned and truncation flag |
| `stale_paths`, `omitted_paths` | Selected sources excluded for a concurrent edit or evidence deadline |
| `objects` (Walk) | Local attachment metadata or external reference receipts; no claim that a remote body was read |

Fragment coordinates are **Unicode codepoints in `search-content.v2` prepared
text**. The source-section range is in canonical Markdown, covering the section;
it is not a character-for-character edit mapping. Consumers must not use prepared
offsets for Markdown mutations. Canonical hashes are checked before packaging and
again at the return boundary, including graph/context dependencies. No search can
promise that a source remains unchanged after its response; a later write must
use revision preconditions.

Lookup and Similar add `outcome`: `matches`, `no_match`, or `incomplete`. With
matches, the packet may still be partial. With no matches and a rebuilding vector
index, the outcome is **`incomplete`**, not evidence of absence. `complete` refers
to the requested bounded operation; it is not a claim of perfect recall. Candidate
channel limits, missing metadata, verification failure, stale evidence and
deadlines are reported. Scoped responses do not expose global index counts.

Walk retains its 0–4 depth and 1–200 object limits, includes reciprocal edges
correctly and raises `GRAPH_CHANGED` if evidence changes during traversal. Walk
does not request text context or fetch Saturn/Chronos bodies. Its attachment and
remote-object records are explicitly reference-only.

## Bounded Lookup planning and context

```python
from mastermind.weaver import Lookup, Scope

result = service.weaver.run(Lookup(
    "Найди материалы про самолёты, авиаконструкторов и прочность композитных крыльев",
    scope=Scope("owner", frozenset(authorized_paths)),
    planning="auto", refine=True, context="section", context_bytes=32768,
))
```

Simple queries and factual questions take one search pass. `auto` recognizes
explicit lists and adds at most three directions; a fourth list item remains in
the last combined direction. `single` disables decomposition. Longer or unclear
lists remain one query. Each direction uses the same scope, filters and original
exclusions. Results are deduplicated by path, preserve the best independently
verified evidence and reserve result slots across directions. `coverage` records
planned queries, discovered/returned paths and unexecuted directions. Coverage of
a combined direction is evidence of a hit for that direction, not proof that every
subclause was answered. No answer text is generated.

Bibliotekar is available only if both the existing Settings checkbox and the
Lookup `refine` flag are enabled. Default Settings remain off. An ambiguous or
empty search may request one proposal, bounded to eight terms and known evidence
handles. Lookup gives this call at most eight seconds within its total 30-second
budget; placement retains its existing budget/checkpoint semantics. Proposed
fields, reference/path syntax and controls are rejected. Terms discover candidates;
the **original query** still verifies them. The model cannot expand scope, alter
filters or authorize a result by inventing a new topic. Overall maximum: original
search + three directions + one refinement. Similar remains independent of this
assistant and keeps its 15-second budget.

`context` supports `none`, `adjacent` (default for Lookup), and `section`.
Packaging starts with up to two matching spans per note. It may add the previous
and next paragraph inside the same section; `section` may also add the nearest
ancestor introduction. Sibling sections and graph neighbors are not silently
included. Overlapping ranges are deduplicated. Match spans are at most 3,200 bytes,
context additions at most 1,600, with a global 0–65,536-byte caller limit (default
32,768). Similar and Placement use 8,192 bytes; Walk requests metadata only.

## Rejection diagnostics and evaluation

`weaver.diagnostics.v1` records candidate/discovery channels, rank before
verification, final rank, bounded numeric signals, verification status and final
disposition. Dispositions distinguish verification rejection, result-limit loss,
source-change rejection, evidence-deadline omission and returned matches. Ranks
before verification belong to the winning search pass in a composite request.
An evaluation label absent from candidate diagnostics is classified as a loss at
candidate generation; filters/scope and channel limits must also be considered.

Private traces persist only allowlisted paths, hashes, stages, scores, reasons
and timings. Query text, fragments and Bibliotekar terms are not persisted there.
Existing retention remains seven days, 10,000 traces and 64 MiB overall, with
64 KiB per trace and explicit truncation of detailed candidate rows.

Measurements use pinned local E5, passage-prefix vectors, zero overlap and exact
Faiss. The 24-case fixed task corpus has separate Lookup/Similar judgments and
six calibration plus six test cases per task. After these cases have informed
development, they are a regression corpus, not a fresh blind estimate.

| Test split (6 cases each) | Before | After |
| --- | --- | --- |
| Lookup hit@3 | 3/6 | 6/6 |
| Lookup recall@5 | 33.3% | 91.7% |
| Lookup false results in first three, total | 0 | 3 |
| Similar hit@3 | 5/6 | 6/6 |
| Similar recall@5 | 83.3% | 100% |
| Similar false results in first three, total | 4 | 1 |
| Lookup median latency | 684 ms | 728 ms |
| Similar median latency | 675 ms | 708 ms |

Across both splits, Lookup false@3 increases from 0 to 6; Similar decreases from
8 to 4. The accepted tradeoff is higher Lookup recall with visible uncertainty,
not a claim that lowering a cutoff solved relevance. Full indexing measured
21.7 → 22.7 seconds; one edit to rebuilt index 2.2 → 1.7 seconds. These are local
runs, not statistically significant speed claims.

The independently authored work-order set contains eight Lookup and four Similar
cases: Russian-to-English retrieval, abbreviation, alias, Russian inflection,
late evidence, multiple topics, lexical distractors and absent material. Lookup
hit@3 including the empty case is 7/8, positive-case recall@5 78.6%, false@3 7.
Similar hit@3 including the empty case is 3/4, positive-case recall@5 66.7%,
false@3 3. These remaining misses/noise are recorded, not hand-cleaned. In
particular, E5 still loses some cross-language paraphrases and may return a weak
match when the requested subject is absent. Rejected positives retain their loss
stage for the next model/reranker comparison. Three directed/limited/isolated Walk
checks and source-edit invalidation passed. Exact aliases, late evidence and
compound-direction coverage have explicit assertions.

The real-model demo50 regression passed for all source notes, including root,
pool, templates, cross-branch relationships and unchanged recommendation order
after moving all 50 files into different directories.

Placement's frozen 100-case test run remains unchanged: 78/78 automatic decisions
correct, zero must-pool auto placements. Disabling vectors yields 62/62 correct.
No placement threshold file or model lock was modified. These runs exercise
retrieval/policy; separate unit tests cover common plan evidence and execution.

The native Core → actual Worker HTTP probe passed authorization, bilingual
retrieval, scope, Similar, Walk, source-edit rebuild and one actual local
Bibliotekar refinement. Its added terms did not authorize an unrelated result.
No external provider key was used. This probe does not replace Linux sandbox,
Docker-stack/native-Obsidian or deployment acceptance.

The first full Python run passed 722 tests with 16 environment skips. After adding
the remaining cases, the repeated run passed 725 and skipped 16, with one Windows
`WinError 5` during a watcher test's direct directory rename. That test passed
separately, then the complete watcher/Crusher group passed 31 tests. The final
targeted Weaver/context/related/chunk suite passed 93 tests. Bridge type checks,
behavior/parser tests, repository validation and exposure inventory passed. This
records the transient failure rather than reporting an entirely clean final full
suite. No watcher test was disabled or weakened.

## Consumer placement profiles

`ConsumerProfile` can be registered through `Weaver(..., profiles=[...])` by
trusted bootstrap code. A profile specifies its name/version, fixed authorized
scope, assessment and decision rules, optional pure renderer and explicit writable
paths. Default: planning only. It cannot be supplied by a public request. Only
Crusher is registered by the production service; the second consumer in tests is
an isolated fixture, not a new product integration.

`Placement.operation` and `ExecutePlacement.operation` are explicit:

- `create_and_link`: existing Crusher flow, new Markdown in `root/crusher` with a
  link from the new note to the selected branch/pool and durable job replay.
- `graph_link`: registered consumer may update 1–16 existing authorized notes
  according to its renderer's link/content policy. It cannot create/delete files
  or write outside its immutable scope and writable-path set.
- `file_move`: explicitly rejected by current profiles; callers cannot get a
  folder move by requesting graph placement. A future move policy must account
  for native links, Shares and identity updates rather than reusing graph writes.

The registry separates preparation from execution, verifies the service instance,
profile/version/operation, source graph revision and optional expiry, and renders
under the coordinator's pause/lock boundary. It checks dependencies again and uses
canonical compare-and-swap commits. Consumer receipts and the plan/content digest
are stored atomically in the existing `operations` journal. Repeating an operation
after success (including a lost response) returns its receipt without another
write; a different payload with the same ID conflicts. Interrupted operations
require recovery and a new plan. No new database schema or alternative writer is
introduced. Tests cover readonly profiles, write limits, stale graphs, replay
across registry reconstruction and a lost response after durable commit.

## Reproduction

Run from the Mastermind checkout using its virtual environment. Model files must
already exist under `.local/models`; these commands neither download models nor
read the operator's Vault. Windows: use `.venv/Scripts/python.exe -X utf8`.

```text
python -m pytest -q
python -m ruff check src tests
python scripts/qualify_weaver.py --facade --output artifacts/weaver-20261006/after.json
python scripts/accept_weaver_tasks.py --before artifacts/weaver-20261006/before.json --after artifacts/weaver-20261006/after.json --output artifacts/weaver-20261006/acceptance.json
python scripts/qualify_weaver_workorders.py --output artifacts/weaver-20261006/workorders.json
python scripts/qualify_related_quality.py --local-root . --corpus tests/fixtures/related_demo50.json --check-demo50 --output artifacts/weaver-20261006/demo50.json
python scripts/qualify_context_indexing.py --local-root . --corpus tests/fixtures/context_indexing/corpus_v3.py --phase test --calibration src/mastermind/weaver/calibration.json --output artifacts/weaver-20261006/placement.json
python scripts/integration/probe_weaver_http.py --output artifacts/weaver-20261006/http.json
```

`before.json` was captured before these source changes; do not overwrite it with
the candidate implementation. The acceptance script rejects a model/configuration
mismatch, recall regression, increased Similar noise, excessive Lookup noise
(at most three extra false@3 per six-case split, precision@3 at least 75%), and
large latency regression. It is a fixed-corpus regression gate; keep the separate
independent work-order report visible when deciding the next quality change.

Ruff passes for `src`, `tests` and the Weaver qualification scripts changed here.
A broader scan of all scripts also reports 19 lint findings in unrelated existing
deployment/fixture/Shared scripts; this work does not modify those files.
