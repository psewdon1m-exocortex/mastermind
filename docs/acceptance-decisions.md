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
- No remote repository exists. Current commits and CI-script executions are local;
  GitHub Actions, publication and production deployment have not been performed.

The remaining work covers the final three-image build, complete Linux checks,
dependency remediation, real native and producer regressions, host installation
and update/rollback recovery, and consolidation of exact-version evidence.

The change needs no data migration and does not change backup compatibility.
Rollback continues to use the encrypted pre-update snapshot and tested group
rollback. Reinstating excluded endurance tests requires a new owner decision.
