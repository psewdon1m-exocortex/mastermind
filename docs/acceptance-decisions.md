# Current acceptance decisions

The owner's explicit instructions on 2026-09-15 supersede the corresponding
Mastermind concept and acceptance requirements. General project Parts 00–12
remain authoritative for every unaffected requirement.

- Development and all active local verification use the main C: drive and its
  Docker Desktop engine. The external WSL migration has been abandoned.
- Do not run an eight-hour stability test. Native acceptance instead executes
  six real editor saves, two coordinated Core mutations, reconnects and one
  streamed representative Vault export. It verifies preserved text, no duplicate
  markers, durable delivery of native Activity to Core, image identity, no OOM
  and no container restart. The runner has a
  15-minute failure deadline, not a minimum waiting period.
- Do not transfer an 8 GiB payload for verification. The host Updater transport
  probe uses 4 MiB, including actual hashing/sealing, cancellation, authorization
  and expiry. An oversized declaration is rejected before payload allocation.
  Representative roughly 350 MiB backup, restore and pipeline checks remain.
- Runtime limits are unchanged. Long-duration stability and actual full-capacity
  8 GiB throughput are **not tested by owner decision**; neither is reported PASS.
- On 2026-09-16 the owner connected `origin` to
  `https://github.com/psewdon1m-exocortex/mastermind.git` and requested the first
  source push and verification CI. Existing recorded test runs are local;
  GitHub Actions results must be recorded separately after an actual run.
  Release publication and production deployment remain separate operations.

The final three-image build, 510-test Linux suite, bounded native and producer
regressions, clean host installation and update/rollback recovery have passed
locally. Remaining release work covers dependency remediation/review, immutable
upstream producer/policy identities and protected publication setup in the newly
connected repository. Physical removal of the stopped external copy and unused C: transfer
credentials was rejected by automatic execution review. See the current
[implementation ledger](IMPLEMENTATION.md) for evidence and exact limitations.

The change needs no data migration and does not change backup compatibility.
Rollback continues to use the encrypted pre-update snapshot and tested group
rollback. Reinstating excluded endurance tests requires a new owner decision.
