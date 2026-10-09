# Central contract alignment

Review date: **2026-10-06**. This is a source/documentation review, not a new deployed
stack, provider, browser or signed-release qualification. The documentation follows
the current workspace `.docs`, including its uncommitted approved decisions.

## Corrections applied to the guides

| Earlier description | Current contract |
| --- | --- |
| Vendored policy snapshot is the effective authority | Central `.docs` / `general` owns the rules; the external pin identifies verification evidence only |
| Archive and mirror must always be enrolled together | Select archive, mirror or both. Reader accompanies mirror; readiness checks only declared capabilities |
| Saturn edits schedules, or paired schedules have separate UI controls | The consuming service owns schedule changes; a paired profile uses one enabled state and interval with separate status/receipts |
| Application update keeps disk preimages/spools for 24 hours | The central saved-copy contract requires transient memory/verified tmpfs and the operator's original ZIP for later recovery |
| Shared-agent release controls are part of service Settings | Host install/check/update belongs to `sudo updater tui`; service Settings manages scoped links and functions |
| Current retrieval is Curator/context-indexing v1 | Weaver/Bibliotekar and `search-content.v2`; legacy storage/routes retain compatibility names |
| September live-provider and image checks describe today's stand | Such records are dated historical evidence; actual current deployment readiness must be observed |

## Remaining implementation and qualification gaps

These findings are not alternate supported contracts. This documentation task does
not change application behavior or close the associated release checks.

| Finding | Central requirement | Inspected evidence and consequence |
| --- | --- | --- |
| Update staging uses the service filesystem | Part 03 §13.2 and Part 05 §34 require bounded memory or verified tmpfs for update bytes, no durable retained archive, and an agreed effective size ceiling | `src/mastermind/updates.py` constructs snapshots/ZIPs under `config.home/recovery/updates` and uses the ordinary backup spool reservation. It cleans new-protocol material but does not establish the required tmpfs-only boundary or a separate 128 MiB default end-to-end update ceiling. Cleanup alone is not conformance. |
| Selective enrollment requires full consumer qualification | The 2026-10-05 decision and Parts 03/09/10 allow archive-only, mirror-only and paired profiles | `web/backup-policy.js` recognizes an unavailable archive and combines controls for paired profiles. `backup_policy.py` still serializes an archive-shaped intent. Require actual enrollment, scheduling, mirror-reader denial/availability and backup/restore tests for all profiles before claiming end-to-end support. |
| Published producer tuple still needs consumer qualification | Parts 05/09/13 require signed compatible producer artifacts and host dependency verification | `docs/compatibility.json` records immutable Updater 0.6.13, Neptune 0.1.13, Saturn 0.2.7 and Chronos 0.2.7 sources, but remains `published: false` until the exact tuple passes the Mastermind host/native suite. Historical patches are not release evidence. |
| New central decisions are not represented by the pinned baseline | Parts 00/12 require immutable effective policy and exact-candidate evidence | The local central checkout has working-tree changes. `policy-lock.json` retains `publication_ready: false`; resolving the referenced catalog must not open signing. |
| Complete current deployment acceptance is unverified | Parts 04/06 require real health, native Runtime, recovery and relevant integration checks | Historical Linux/native/live-provider passes belong to their recorded sources. Weaver's 2026-10-02 record left its stack/Linux gates open; later UI fixtures do not close them. |

Before implementing an affected migration, use Part 00's divergence procedure:
record the exact rule, implementation, impact, implementation/compatibility options,
selected path and acceptance/rollback evidence. The user's documentation alignment
request authorizes correcting descriptions and removing policy duplication, not a
silent update-storage or enrollment migration. Independent documentation cleanup
and policy-reference verification can proceed without that runtime decision.

## Scope of this review

All Parts 00–13 were mapped to Mastermind's documentation domains in
[Governance](governance.md). The focused comparison covered ownership, UI workflows,
secrets, exposure, backup, updates, host dependencies, retrieval and evidence claims.
This is not a claim that every central requirement has passed implementation audit.
The seven-area impact review remains mandatory on the exact revision before a push.
