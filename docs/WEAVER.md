# Weaver

Weaver is Mastermind's internal graph work engine. It retrieves information,
compares notes, traverses references and executes placement requested by Crusher.
Bibliotekar is its optional local AI search-refinement assistant.

## Authority and implementation scope

The workspace `.docs/PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md` is authoritative;
the [vendored policy index](policy/README.md) documents the standalone snapshot.
This change preserves the existing Core/Worker trust boundary,
private Bridge authentication, canonical Vault coordinator and schema-2 durable
Crusher jobs. It does not publish a release or modify sibling services.

| Guide | Applicability and verification |
| --- | --- |
| Part 01 | Combined Obsidian/Weaver Settings, accessible existing controls, embedded documentation |
| Part 02 | Bounded timing/evidence diagnostics; no raw editor buffers or credentials in logs |
| Part 03 | Settings and job checkpoints mandatory; vectors and indexes derived; restore/rebuild tests |
| Part 04 | Core/Worker packages and health; no new deployment unit or listener |
| Part 05 | Pinned native search dependency, previous-data compatibility, candidate startup |
| Part 06 | Regression, quality, performance and integration evidence collected separately |
| Part 07 | Scoped retrieval before ranking, canonical source verification, mutation authority |
| Part 08 | N/A: no public indexable surface is added |
| Parts 09–13 | Shared-agent ownership/installers unchanged; inspect integration regressions |

## Verification record

Baseline revision: `0caf638`. Before implementation, the semantic, related-note,
context-indexing, Curator and Crusher suites passed: **92 tests**.
Real-model reports are written to `artifacts/weaver/` using synthetic data only.
This document describes the implementation added on 2026-10-02. Older
context-indexing ledgers describe earlier revisions, not acceptance of this one.

Final native suite: **655 passed, 16 skipped**, 113.5 seconds. The skipped platform
checks still require Linux. An earlier run hit the existing Windows watcher rename
race; its isolated replay and the final full run passed. Python lint, repository
policy/link validation, all 170 exposure entries, Bridge TypeScript/parser/lifecycle
tests and build, 16 Bridge release tests, and wheel contents/calibration verification
passed. The wheel is a local build artifact, not a published release.

## Responsibilities and work orders

Weaver is a module in Core, not a fourth container, autonomous background agent or
public API. Its facade is `mastermind.weaver.Weaver`. Core owns one instance at
`service.weaver`; consumers submit typed requests through `run()`.

| Request | Result and authority |
| --- | --- |
| `Lookup(query, scope, filters, deadline, limit)` | Up to 20 (maximum 50) supported note matches, scores and evidence; no generated answer or writes |
| `Similar(path, text, focus, scope)` | Up to eight related notes from the current, possibly unsaved editor buffer; never saves that buffer |
| `Walk(path, scope, direction, depth, limit)` | Bounded graph fragment of notes and referenced objects, with edges and revision identity |
| `Placement(understanding, text, snapshot, profile, operation_id, deadline)` | Policy-controlled placement recommendation with source receipts; currently the `crusher` profile |
| `ExecutePlacement(job, content, plan, profile)` | Canonical creation through the existing durable Crusher journal and coordinator; returns the commit receipt |

Example, from an already authenticated internal consumer:

```python
from mastermind.weaver import Lookup, Similar, Walk, Scope

scope = Scope("owner", frozenset(authorized_paths))
matches = service.weaver.run(Lookup("Как птицы ориентируются?", scope=scope))
related = service.weaver.run(Similar(path, editor_text, focus=cursor_text, scope=scope))
fragment = service.weaver.run(Walk(path, scope=scope, direction="both", depth=2, limit=64))
```

Scope is supplied by the authenticated adapter, never taken on trust from a
public request. Public Shared and Crusher visitors cannot query Weaver. Scope is
applied before candidate limits, statistics, graph expansion and vector scoring.
An empty result is valid; Weaver does not fill the list with weak matches.
`Lookup.deadline` uses monotonic time; placement keeps the durable job's Unix
deadline and translates it into a bounded monotonic retrieval budget.

### Objects and traversal

Graph movement follows resolved references, not filesystem nesting. `Walk` supports
outgoing, incoming and both directions, depth 0–4 and at most 200 objects. Cycles
are visited once. A changed source revision rejects the walk with `GRAPH_CHANGED`.

Objects include notes, local attachment metadata, Saturn resource references and
Chronos event references. Local attachments expose identity/path/size within
scope; their binary contents are not embedded or read by traversal. Remote
objects have `availability: unverified`: a link is not proof of access or existence.
Their bodies still require the existing authorized service resolvers. Weaver
currently searches note text and human resource labels, not arbitrary remote
object contents. There is no multimodal attachment index in this change.

### Placement belongs to Weaver; policy belongs to the consumer profile

Crusher retains acquisition, extraction, understanding, generation, validation,
job acceptance and progress. Weaver performs retrieval, branch selection, final
revalidation and placement execution. The separate
`weaver/policy.py` implements **Crusher's** constraints; these constraints do not
limit `Lookup`, `Similar` or `Walk`.

The allowed graph route is root → `#main` → nested `#key`. Ambiguous structure,
contradictory evidence or insufficient confidence selects the configured pool.
Files always go to `root/crusher`, using a unique basename and the frozen template.
The **new note** links to the selected branch/pool. Parents are not rewritten.

`weaver/execution.py` uses the existing coordinator boundary and source hashes,
revalidates the plan, checkpoints the commit and writes through the one canonical
mutation journal. Retry/restart must not create a duplicate note. It cannot accept
a job from a different service instance. This is deliberately a typed, trusted
job adapter, not an API allowing arbitrary graph mutations. A new consumer needs
an explicit registered placement policy and mutation authority.

## Retrieval and evidence

The pipeline remains: query preparation → authorized graph snapshot → parallel
retrieval channels (FTS/BM25, E5 vectors, entities, metadata, real graph links and
branch profiles) → candidate fusion → reranking → bounded graph expansion →
consistency/confidence assessment → optional Bibliotekar refinement and one
second retrieval. Placement additionally applies its consumer policy and checks
the current hierarchy before commit.

`search-content.v2` provides the same deterministic preparation for indexed text
and queries. Technical YAML, structural tags, opaque IDs and URL targets are
removed; human labels, topical metadata and prose remain. Canonical Markdown is
never rewritten for recommendation quality. Scope-local repetition detection is
an additional verification step applied to both source and candidate evidence.

Chunks respect Markdown sections, carry heading context and prefer paragraph
boundaries. Long sections split within the E5 token budget; heading and model
prefixes leave headroom below 512 tokens. Chunk receipts contain the prepared-text
offsets, original section ranges, source SHA, model/representation identity and
chunk ID. Prepared offsets must not be used directly to edit original Markdown.
Overlapping passages are deduplicated before verification.

Reranking verifies **retrieved passages**, including a match late in a long note,
instead of comparing every hit only with the document opening. Up to two candidate
passages enter verification. Actual token boundaries split bounded comparison
inputs; excessive inputs fail explicitly instead of silently truncating. Excerpts
prefer the verified evidence. Generic repeated titles cannot independently
authorize a match. The same rule applies to ordinary, root, pool and template
notes; there is no service-note blacklist or directory relevance bonus.

Interactive lookup and note similarity are separate tasks and evaluation sets.
They share preparation and retrieval infrastructure, but can use different
document-prefix representations. Interactive calls disable Bibliotekar so typing
does not initiate an expensive reasoning call.

## E5 modes and the exact engine

The pinned local multilingual E5 model produces normalized 384-dimensional vectors.
The working default remains query-prefix input versus passage-prefix documents,
with zero overlap. The measured alternatives are `similarity_mode="query"`
(query-prefix documents for note similarity) and overlap 32/64 tokens. Query mode
stores a separate disposable representation; ordinary information retrieval still
uses passage vectors. These are constructor/qualification options, not GUI choices.

This follows the E5 authors' distinction between asymmetric retrieval and
symmetric similarity, while requiring a local comparison before changing defaults:
[official E5 model card](https://huggingface.co/intfloat/multilingual-e5-small#faq).

`vector_engine.py` uses exact Faiss `IndexFlatIP` on normalized vectors. SQLite
remains the durable, disposable vector store. Core scores scoped blocks of at most
2,048 rows, retains at most 32 MiB of content-addressed native blocks and uses two
native threads. It does not keep an unbounded second copy of the whole index or
load native index files supplied by a user. Results are restored to stable source
row order; near ties may differ only within float32 tolerance.

`backend="python"` retains the exhaustive oracle. An unavailable Faiss import uses
that backend with `FAISS_UNAVAILABLE` in engine status. Invalid dimensions, NaNs or
corrupt vectors require rebuilding. This is exact search, not HNSW/ANN; PostgreSQL,
pgvector and a separate vector database are not required at the current scale.
[Faiss index reference](https://github.com/facebookresearch/faiss/wiki/Faiss-indexes).

## Bibliotekar

`weaver/bibliotekar.py` owns the bounded refinement contract;
`bibliotekar_runtime.py` runs the pinned local Qwen model in Worker. Bibliotekar
may propose search terms and known evidence handles. It cannot choose a final
destination, expand scope, run tools, mutate notes or call an external provider.
Its budget remains one reserved call, 6,000 input tokens, 1,000 output tokens and
45 seconds inside the placement budget. Saved responses are reused after restart;
an interrupted reservation is not silently repeated.

The combined **Obsidian & Weaver** Settings card contains the pool path, template
path, fixed Crusher directory, Bibliotekar checkbox and readiness. Default: off.
Requested and effective availability remain separate. Settings retain their
revision, validation, idempotency and concurrent-edit protection.

## State, upgrade and recovery

| State | Treatment |
| --- | --- |
| Vault files, attachments, templates, configuration, accepted job snapshots and commit receipts | Mandatory; existing backup/restore and mutation rules |
| Semantic documents/text/chunks, query-prefix variants, FTS, graph metadata, branch profiles | Derived; discard and rebuild from authorized canonical data |
| Faiss blocks, comparison vectors and token plans | Bounded process caches; not persisted or backed up |
| Retrieval diagnostics | Existing bounded allowlist; no raw editor text, credentials or note bodies |

The authoritative database schema remains **2**. The added `semantic_variants`
table is derived and excluded from logical backups. Representation/overlap changes
invalidate derived vectors and branch profiles. Source edits/deletions immediately
exclude stale rows; a bounded background rebuild restores availability. Both
representations together are capped at 300,000 vectors (about 440 MiB of vector
payload, plus SQLite/text overhead). Query mode therefore has a storage and rebuild
cost. Model digest changes require explicit reindex confirmation.

No destructive rename of persisted settings or job stages occurs:

- `service.context_indexing`, `ContextIndexing` and old Python modules alias Weaver.
- Stored `context_indexing`, `curator_enabled`, Curator checkpoint fields and
  `/api/owner/context-indexing/*` remain compatible.
- The settings response accepts/exposes `bibliotekar_enabled`; contradictory old
  and new fields are rejected. Old clients continue to work.
- Worker `/curator/*`, `MASTERMIND_CURATOR_*`, lockfiles and artifact paths remain
  stable deployment identifiers. New source/UI names are Bibliotekar.
- Qualified placement thresholds now live in `weaver/calibration.json`, bound to
  `search-content.v2`, model and corpus hashes. Unqualified combinations use pool.

Rebuild Core and Worker together to deploy this change. The old runtime may rebuild
derived data for its own representation on rollback; use the managed rollback or
compatible backup workflow for authoritative state. This task does not deploy a
candidate into the existing local Vault or publish an update.

## Measurement record and decisions

All measurements below used synthetic data, the pinned real E5 model and local
CPU execution. They do not imply universal recommendation accuracy.

The long-note bilingual corpus has 12 distinct topics, 26 documents and separate
calibration/test topic groups. Each group has six lookup and six similarity tasks.
Labels are authored and intentionally strict. The test set was examined during
development, so these results are regression evidence, not a pristine blind study.

| Variant | Test lookup hit@3 | Test similarity hit@3 | Similarity false matches in top 3 | Full index / one edited long note |
| --- | --- | --- | --- | --- |
| Previous implementation `0caf638` | 1/6 | 0/6 | 18 | Baseline report |
| Weaver passage, overlap 0 | 3/6 | 5/6 | 4 | 20.1 s / 1.63 s |
| Weaver query, overlap 0 | 3/6 | 5/6 | 4 | 39.4 s / 3.25 s |
| Weaver passage, overlap 32 | 1/6 | 4/6 | 4 | 22.5 s / 1.89 s |
| Weaver passage, overlap 64 | 1/6 | 4/6 | 4 | 22.8 s / 1.83 s |

The selected variant's lookup recall@5 is 0.333; similarity recall@5 is 0.833.
Lookup produced no judged false matches, but missed relevant notes. Similarity
still produced four judged false matches. Improving precision and multilingual
recall remains measurable follow-up work; this change does not claim perfect
semantic understanding. Selected test p50/p95 were 660/666 ms for lookup and
674/690 ms for similarity. Embedding, verification and SQLite work remain part of
total latency. Prefix and overlap variants are retained for reproducible experiments,
but are not enabled merely because their names suggest an improvement.

The separate 50-note thematic regression passed all seven checks: engine-topic
recommendations, all five main hubs, pool behavior, universal root/pool/template
eligibility, useful cross-branch links, clean excerpts and identical recommendation
order after moving **all 50 notes** into unrelated directories.

Exact-engine benchmark: 12,000 normalized vectors, 384 dimensions, 20 queries.
Python p50/p95: 574.6/604.3 ms; Faiss: 15.4/16.2 ms. The top ten matched for every
query, maximum score delta was `4.23e-8`; compute-only median speedup was **37.3×**.
Faiss retained 18.4 MB of blocks; measured process RSS was 146 MB. This benchmark
does not include model inference or prove a 37× end-to-end speedup.

Placement thresholds were frozen on 100 calibration cases, then checked on 100
separate test cases. Complete retrieval made 78 automatic decisions, vector-disabled
retrieval 62, profiles-disabled 77 and expansion-disabled 78. Bibliotekar made two
refinements and increased automatic decisions to 80. Every automatic decision in
these test runs was correct and no must-pool case was placed automatically.
Calibration itself contained one incorrect automatic decision out of 74; the
acceptance target is at least 98% observed precision, not a guarantee of infallibility.
Bibliotekar's small measured benefit does not change its default-off policy.

Real Core classes → Worker HTTP checks passed: private authorization, bilingual
retrieval, similarity, scoped results, graph traversal and edit/rebuild invalidation.
Real Bibliotekar was ready; the separate placement run exercised two real calls.
The browser Settings probe passed validation, note picker, stale revision conflict,
draft preservation, rebasing and narrow/wide layouts.

Docker Desktop could not start its Linux engine because its local inference Unix
socket returned a Windows filesystem error. Consequently this change has **not**
yet been rechecked in the three-container stack/native Obsidian or under Linux
sandbox and cgroup limits. Native HTTP/model tests do not replace those gates.
No external generation key was read or used. No current paid-provider end-to-end
quality or sibling-service live integration claim is made.

## Reproduction and next deployment gate

```text
python -m pytest -q
python -m ruff check src tests
python scripts/validate_repository.py
python scripts/exposure_inventory.py
npm --prefix bridge run check
npm --prefix bridge test
npm --prefix bridge run build
python scripts/qualify_weaver.py --output artifacts/weaver/tasks.json
python scripts/qualify_weaver.py --mode query --output artifacts/weaver/query.json
python scripts/qualify_weaver.py --overlap 32 --output artifacts/weaver/overlap32.json
python scripts/qualify_weaver_exact.py --output artifacts/weaver/exact-benchmark.json
python scripts/integration/probe_weaver_http.py
python scripts/integration/probe_weaver_ui.py
python scripts/accept_weaver_calibration.py --reports artifacts/weaver
```

On Windows use the project virtual environment and `python -X utf8`. Real-model
native probes expect the already verified model files under `.local/models`;
they use isolated temporary Vaults and remove their disposable credentials.
`qualify_context_indexing.py` and `qualify_related_quality.py` remain compatible
qualification entry points for the pinned Worker image; their default model paths
are the container paths. The accepted threshold file contains report digests.

Before release: commit the reviewed candidate, run the normal clean-revision CI
with images, the Linux sandbox/resource gates, and the bounded native Obsidian
probe against the rebuilt Core/Worker. Run live external-provider acceptance only
with an explicitly configured authorized provider. Existing pending component
pushes/CI and their commits were not rewritten or superseded by this work.
