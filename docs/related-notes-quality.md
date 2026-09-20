# Related notes quality: implementation and verification

Verified locally on 2026-09-20, including the follow-up correction for overview notes.
This is regression evidence on authored fixtures,
not a universal estimate of recommendation accuracy.

## Delivered behavior

- `search-content.v1` creates disposable semantic text without technical YAML,
  structural tags, opaque service IDs or link destinations. Topical metadata and
  human link labels remain searchable. Canonical Markdown is unchanged.
- Knowledge lookup detects repeated sentences and adjacent short blocks within
  its authorized, bounded sample. Recurring headings and resource captions cannot
  establish a topic match. Individual topical headings and repeated subjects survive.
- Unfilled template fields and headings of empty sections supply no factual text.
  A second, bounded local E5 comparison checks cleaned evidence before acceptance;
  retrieval cosine alone cannot authorize a recommendation. Titles are scored
  separately instead of being prepended to semantic prose.
- Short outlines may use bounded passages from actual linked notes, without
  requiring #main/#key or inferring a topic from filesystem directories.
- Each recommendation needs topical or contrasting semantic evidence. The result
  may contain fewer than eight items or no items. Lists of links/headings still
  match explicit topics, but their shared shape is not descriptive evidence.
- Root, pool and templates participate as both sources and candidates under the
  same content rules. There is no service-note category, path denylist or disabled
  source message. No canonical note was edited to fix a recommendation.
- Native cards show link/similarity reasons and cleaned, preferably substantive
  excerpts. Curator and Crusher placement remain separate from interactive lookup.
- Representation changes automatically rebuild disposable vectors and text;
  calibration is explicitly bound to the representation before automatic placement.

The content and retrieval contracts are documented in [context-indexing](context-indexing.md)
and [API](api.md). The native pane inherits Obsidian appearance as required for Vault.

## Verification

| Check | Result |
|---|---|
| Full Python suite in Linux, the service environment | 649 passed; 154 seconds |
| Final targeted context-indexing, semantic and Related notes tests on Windows | 91 passed after the final disabled-vector guard; covers short blocks, topical headings, copied content, all note roles, model/cache invalidation, failure/deadline handling and late/cursor context |
| Bridge TypeScript check and tests | Passed, including parser parity, lifecycle and stale response rejection |
| Actual Obsidian + Core + local E5 | 7 checks passed: aviation suggestions, keyboard change to gardening, Russian-to-English retrieval, opening a suggestion, hiding the pane, empty buffer, connection recovery |
| Synthetic 50-note thematic Vault | All five main overviews reject unrelated sibling topics based on shared scaffolding; engine hub's four subject notes rank first; hybrid drive retains the battery across branches |
| Universal note eligibility | Pool finds root and the materials catalog from its actual description; root, pool and template also find the hybrid note when given topical unsaved text |
| Directory relocation in the isolated 50-note Vault | Recommendation order preserved for all 50 sources, including root/pool/template; canonical text preserved |
| Crusher placement compatibility | Stored representation, thresholds and placement policy are unchanged by this follow-up; the previous 100-case replay in each of five modes remains applicable, and placement tests are included in the full suite |
| Running local stand | 13 Bridge requests passed, including all five main topics and topical unsaved buffers in root/pool/template; index READY 50/50; all 50 canonical hashes unchanged; installed Bridge matches built hashes |

Both screenshot examples now keep their topical sub-branches without suggesting
unrelated main hubs from shared section labels. `pool` returns `root` and the
materials catalog based on its actual operational description. The 50-source
offline run measured median 427 ms and maximum 2,526 ms under a two-CPU limit;
these are local fixture timings, not production latency guarantees.

Placement modes were complete, vectors unavailable, profiles disabled, expansion
disabled, and Curator enabled. Complete and Curator-enabled runs each placed 80/100
cases automatically; the lexical fallback placed 62/100. Curator was not invoked by
these cases, so this replay demonstrates no new Curator benefit. Frozen thresholds
were retained, and representation regression provenance is recorded in
`src/mastermind/context_indexing/calibration.json`.

The first correction missed short repeated labels such as “Учебное занятие” and
“Событие Chronos:”; the five main overviews were not asserted in its acceptance set.
This follow-up adds those assertions, general short-block fixtures in two languages,
and removes the former root/pool/template exceptions rather than editing note data.

The follow-up native test also caught a Russian-to-English regression caused by
injecting filenames into semantic prose. The corrected implementation passed the
same native test, without lowering the cosine threshold. Long buffers retain evenly
sampled source passages and cursor context during final verification.

Earlier runs exposed and resolved a multilingual acceptance regression. The full
Windows suite also encountered an existing directory-watcher rename restriction
(`WinError 5`); that test passed in the full Linux run. The initial Linux container
used a 512 MiB temporary filesystem and correctly failed capacity guards; the final
run used an isolated ordinary Docker volume, which was removed afterward. A local
deployment waiter's old HTTP session timed out; independent authenticated checks
confirmed readiness, complete indexing and unchanged canonical hashes.

## Reproduction

Fast tests:

```text
python -m pytest tests/test_knowledge_quality.py tests/test_related_notes.py tests/test_semantic.py tests/test_context_indexing.py tests/test_context_curator.py
npm --prefix bridge run check
npm --prefix bridge test
```

Real-model thematic regression, inside the pinned Worker image with networking
disabled and the repository mounted read-only at `/suite`:

```text
PYTHONPATH=/suite/src:/suite/scripts python /suite/scripts/qualify_related_quality.py --corpus /suite/tests/fixtures/related_demo50.json --check-demo50 --output /report/related-quality.json
```

Native UI: build Bridge, then run `scripts/qualify_related_notes.py` with the local
Runtime and Worker images. It creates and removes its own synthetic Core/Obsidian
stack. It does not use the owner's Vault or a provider API key.

For full Linux tests, use a disposable ordinary filesystem with sufficient reported
free space for recovery capacity checks, rather than a small tmpfs. This does not
require allocating or transferring an 8 GiB file.

Local detailed evidence from this run is in `.local/related-audit/` (quality,
placement, Linux JUnit and live endpoint reports) and `artifacts/related-notes/`
(native qualification report and screenshots). Those generated directories are
intentionally excluded from Git. The reusable synthetic corpus and runners are tracked.

Cleanup of this follow-up's three disposable native fixtures and test volume was
rejected by the local automatic approval policy (`blocked by policy`, with no more
specific reason). They remain in `.local/mastermind-related-*` and the named Docker
volume `mastermind-related-quality-v2-tests`; this does not affect the running stand.

## Limits

Repetition statistics use a bounded scope-local sample, and semantic verification
checks at most 64 candidates with a 256-vector in-memory cache. No provider API key
or external AI endpoint is used. Lexical matching is Unicode
word matching, not a complete morphological analyzer. Semantic acceptance is a
conservative ranking heuristic, not a probability; small homogeneous corpora or weak
cross-language signals may yield no suggestions. Larger real-world labeled corpora
are needed before claiming broader precision or introducing another reranking model.
