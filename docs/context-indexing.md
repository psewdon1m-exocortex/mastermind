# Context-indexing

Context-indexing is Mastermind's reusable local retrieval engine. Crusher is its
first consumer. The [approved specification](../mastermind_retrieval_curator_pipeline_final.md)
defines the product contract; the [qualification ledger](CONTEXT_INDEXING_IMPLEMENTATION.md)
records measured results and their limits. No public search endpoint or agent
tool execution is introduced.

## Data flow and authority

1. Query processing extracts bounded text, entities, metadata filters and source
   features. Up to eight source samples retain coverage of long material.
2. An authorized immutable graph snapshot feeds independent FTS/BM25, local E5
   vector, entity, metadata/temporal, graph and branch-profile channels. Ordinary
   notes participate, whether or not they have structural tags.
3. RRF combines candidates; explicit semantic/lexical features rerank them.
   Related-note expansion follows real edges in both directions, then the whole
   union is reranked. Provenance retains source paths and content hashes.
4. Consistency and confidence assessment distinguish sufficient, ambiguous and
   insufficient evidence. Scores are ranking measures, not model probabilities.
   Conflicting source paragraphs and explicit topic exclusions prevent an
   automatic placement; Curator cannot reinterpret those as affirmative support.
   The current conservative exclusion guard also uses pool when the excluded
   topic cannot be mapped reliably to a technical anchor name. This can reduce
   coverage for material containing a legitimate topic contrast.
5. If enabled, available and useful, Curator can suggest bounded terms and known
   evidence handles. One further retrieval and union rerank follow. It cannot
   name an authoritative destination, expand scope or invoke tools.
6. Crusher's separate policy selects a unique reachable `#main`/`#key` anchor.
   Cycles, multiple structural parents, conflicting roles and stale evidence
   cannot authorize placement. Otherwise it chooses the configured pool.
7. Generation returns typed title, summary and body. A frozen Markdown template
   produces the document; Core supplies the verified link and provenance. The
   coordinator revalidates and commits it exactly once.

Only the source, structured understanding and bounded template structure reach
the external generation provider through Wyvern → Kernel/Volt. Retrieved Vault
content, profiles and embeddings remain local. Curator runs in the private Worker;
it has no Vault mount, provider credential, remote fallback or write authority.
Shared and public Crusher principals cannot inspect search results or traces.

## Files, graph and Settings

The combined **Obsidian & search** Settings card contains:

| Field | Contract |
| --- | --- |
| Output directory | Read-only `root/crusher`; every new Crusher file is here |
| Pool note | Default `root/pool.md`; graph fallback, not the output directory |
| Template | Default `root/templates/example crusher.md` |
| Curator | Off by default; requested and effective readiness shown separately |

An existing root is required (default `root.md`). Initialization creates missing
default pool/template files and connects root to pool once through the canonical
coordinator. Existing files are never replaced. Per-job placement writes only
the new note's outgoing link; it does not append links to parent notes.
Old Crusher files stay where they were created.

Template placeholders: `{{title}}`, `{{date}}`, `{{time}}`,
`{{crusher.summary}}`, `{{crusher.body}}`, `{{crusher.sources}}`,
`{{crusher.links}}`. Body and links are mandatory, each placeholder may appear
once. Substitution is single-pass; frontmatter and code cannot contain slots.
Templates are static Markdown, not Obsidian Templates/Templater execution.
Structural tags, system markers, secrets, executable markup and injected
references are rejected. Core creates the source and branch links.

Accepted jobs snapshot template bytes/hash, configuration revision and timezone.
Editing a template affects future jobs. Canonical rename follows the pool/template
identity; observed deletion marks it for explicit rebind. Recreating that path
does not silently bind another note. A delete/recreate entirely between external
filesystem observations cannot be distinguished from an edit without a native
identity event; this is an explicit observation boundary.

Apply uses expected revision and an idempotent operation ID. A concurrent change
returns a conflict; draft values remain visible. Validation does not save.
Invalid configuration moves a job to `WAITING_CONFIGURATION`, frees the Worker
and retains its draft. Correct configuration and explicitly resume against the
current revision. Valid understanding/generation checkpoints are reused; template
changes invalidate generation. The original 60-minute job deadline is not reset.
Terminal source data and frozen template snapshots are cleaned; minimal receipts
retain configuration revision and template hash. Failed material expires by 24h.

## API and bounded execution

All routes below require an owner session; unsafe methods also require CSRF and
the canonical origin. All are under `/api/owner/context-indexing`.

| Method and suffix | Meaning |
| --- | --- |
| GET `/settings` | Nested `crusher` / `retrieval` values, revision and readiness |
| PATCH `/settings` | Atomic values with `expected_revision` and `operation_id` |
| POST `/validate` | Validate the same draft without saving |
| POST `/initialize` | Idempotent initialization; empty object body |
| GET `/waiting` | Owner-only jobs waiting for configuration |
| POST `/jobs/{id}/resume` | Explicit revision-bound, idempotent resume |

The managed Obsidian Bridge is another consumer: `POST /internal/bridge/related-notes`
accepts the current note path plus bounded `text`, optional `focus` and `sampled`.
It requires the private Bridge identity; owner cookies and public Crusher tokens
do not authorize it. Core returns at most eight `{path,title,excerpt}` items with
`degraded` and `sampled` flags. This read-only lookup excludes the source and the
configured root/pool/template before retrieval, disables Curator and does not call
placement or generation. See [Related notes](mastermind-bridge.md#related-notes).

Generic retrieval is a Python service interface, with owner/service scope applied
before channel limits, profile construction and expansion. Scoped profiles cannot
replace the global cache or obtain private member terms through its FTS index.

Limits: query 16 KiB; 50 candidates/channel; 300 initial union; 100 fused;
200 reranked; two graph hops and 64 one-hop expansions; profile 12 member notes
× two chunks; two simultaneous retrievals. One pass is bounded to 15 seconds,
the entire placement to 90 seconds. Partial/unavailable strategies select only
their separately qualified calibration; unknown combinations safely use pool.
Changed model digests cannot reuse a qualified vector calibration.

Curator: pinned Qwen3-0.6B Q8_0 GGUF and llama.cpp CPU runner, at most 6,000 input
tokens, 1,000 output tokens and 45 seconds. Durable reservation precedes the
single call. Interrupted reservations are never reissued; replay reuses a saved
response. An unavailable/invalid/late response yields explicit degradation.
Worker serializes heavy tasks, uses embedding microbatches of two and stays
within its configured 2 CPU / 2 GiB limit. Core has 2 GiB, Runtime 3 GiB.

Evidence hashes are checked before commit. Stale placement can be recomputed
once within the original deadline, then uses a valid pool. A missing pool blocks
the write rather than losing the draft. Canonical compare-and-swap, native writer
quiescence and the durable mutation journal remain the final authority.

## Installation, persistence and rollback

Fetch pinned artifacts before building with `scripts/fetch_embedding_model.py`
and `scripts/fetch_curator_model.py`. Downloads occur during preparation, never
as an inference fallback. The Curator lock binds model, runner archives and
license; runtime verifies extracted inventories. Core/Worker must be rebuilt
together when contracts or pinned models change. The qualified calibration is
included as package data, with corpus/model/report hashes.

State schema is **2**. Opening schema 1 migrates idempotently; older Core rejects
schema 2. Do not point an old image at migrated state. Update recovery uses its
physical preimage, or restore a compatible encrypted backup through the managed
restore workflow. Configurations, templates and completed note/commit records
are authoritative; metadata, profiles, traces and vector/FTS projections are
derived and rebuilt. Backup import supports schema 1 and 2.

Local traces are bounded allowlisted diagnostics: no raw query, note text or
credentials. They retain at most 7 days, 10,000 rows and 64 MiB; each trace is
at most 64 KiB. Qualification artifacts contain only deliberately synthetic
material. Production logs do not dump provider packets.

## Quality boundary

The accepted grouped synthetic corpus has 500 cases, including 100 independently
held-out cases from new domains. Default mode automatically placed 80/80 correctly
and sent all 20 must-pool cases to pool. A matched 30-case real-provider legacy
comparison had 10 correct automatic placements for both implementations.
These are observed fixture results, not a universal accuracy guarantee.

Two earlier evaluations failed and are retained in the ledger. A live test also
exposed a negative topic statement with a technical anchor name; an additional
rejection guard fixed it without changing thresholds. After these final
counterevidence guards, the same test cases serve only as regression:
80/80 correct, but zero Curator invocations. Real local inference, response replay
and second retrieval are qualified separately. **No placement-quality benefit
from enabling Curator has been demonstrated; keep it off by default.** Fresh
held-out domains are required before claiming an improved operating point.
