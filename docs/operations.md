# Operations

For releases, `mastermind update check` discovers an approved candidate, `mastermind update apply <version>` starts a whole-group update, and `mastermind update status` observes its durable progress. `mastermind update previous` lists the verified previous version; `mastermind update rollback --job <id> --yes` returns to it using a fresh backup and preserves compatible current data. These commands use the running Core's private admin socket.

Run host commands from `/opt/exocortex/mastermind`. `mastermind-install status` describes containers; `mastermind-install doctor` checks canonical state and authenticated dependencies separately. The Core CLI talks to a private same-container Unix socket and does not publish administration over TCP.

```sh
sudo mastermind-install status
sudo mastermind-install doctor
docker exec mastermind-core-1 mastermind vault validate
docker exec mastermind-core-1 mastermind reindex
docker exec mastermind-core-1 mastermind graph rebuild
docker exec mastermind-core-1 mastermind replication status
docker exec mastermind-core-1 mastermind replication reconcile
```

## Startup and shutdown

Use `docker compose -f compose.production.yaml up -d --no-build` with the installed `.env`. For planned maintenance, finish pending owner operations and stop the owned group with `docker compose -f compose.production.yaml stop core runtime worker`. Do not use `down --volumes`. Runtime restart uses `docker compose -f compose.production.yaml restart runtime`; Core detects the new supervisor and repeats recovery/Bridge startup. Check readiness and the native editor before returning to work. A process kill is a fault test, not the normal way to save an active editor.

## Readiness and failures

`READY` requires canonical storage and authenticated dependency checks. `live`, `canonical_ready`, dependency status and external edge verification are independent. Missing observations are UNKNOWN, not zero. `NATIVE_OWNER_SETUP_REQUIRED` requires the first native trust step described in [deployment](deployment.md). `BRIDGE_UNAVAILABLE` after prior successful setup needs Runtime/log inspection. Do not override quiescence or manually remove a mutation journal.

`NOT_READY`, duplicate basenames, missing opaque data, `RECOVERY_REQUIRED` or `POST_RESTORE_RECOVERY_REQUIRED` stop writes. Preserve the entire service volumes and recovery directories before investigating. Correct an independently understood configuration/storage problem and restart the group to run journal recovery, then repeat `vault validate` and doctor. An unresolved generation/rollback marker requires recovery from a verified archive, not an ad hoc database edit.

If Kernel or Volt is unavailable, restore its own bootstrap/trust first. Mastermind recovery keys cannot be recovered solely from an archive encrypted by those keys. If Neptune is partial or unavailable, Settings distinguishes the state; retrieve a fresh setup code and use Repair. Archive and mirror success times/generations are separate. Saturn owns schedules, quotas, remote commands and revocation.

## Backup, restore and updates

Settings → Backup creates a full encrypted snapshot, supports streaming download and stages ZIP inspection before an explicitly confirmed restore. The equivalent CLI is:

```sh
docker exec mastermind-core-1 mastermind backup create
docker exec mastermind-core-1 mastermind operation OPERATION_ID
```

The resulting staged operation is retained for at most 24 hours; inspect its ID, size and SHA-256 before download. CLI `backup create --output /tmp/recovery.zip` requires an exclusive writable destination in that container. CLI `restore inspect /tmp/recovery.zip` and `restore apply /tmp/recovery.zip --yes` require a bounded regular source file, not a symlink/FIFO. Keep recovery keys outside the archive. See [backup-restore](backup-restore.md).

Settings → Updates checks the approved repository through the own host Updater. A compatible exact version can be applied after confirmation. Core prepares a recovery snapshot and retains the write barrier; Updater applies all three components and accepts only functional health. An interrupted response is reconciled through durable job identity. Failed migration/health triggers restoration of prior components and pre-update data. A failed rollback remains blocked and is never displayed as success. See [releases](releases.md) for release and rollback qualification.

## Diagnostics and retention

Settings contains a bounded log tail and a redacted archive download. Audit records omit raw credentials and note bodies. Use the configured Docker JSON log rotation and inspect free space on the actual Vault filesystem. Failed sources, completed operation spools and old restored generations have bounded retention; active uploads/download leases are protected. Do not clear the backup/recovery spool while an operation or host update is pending.

Logs and reports are not permission to expose internal URLs, `.env`, cookie values, provider keys, full Vault notes or original plugin configuration in a support message. Report the exact service version, operation/job ID, sanitized error code, stage and relevant bounded test evidence.

If a Runtime pause or native preparation response is lost before a mutation starts, Core cancels that exact identity and retries the cancellation after connectivity returns. Runtime rejects a delayed request carrying an already-cancelled identity. A lost safe resume response uses the same reconciliation. This does not release a retained update/recovery barrier. The cancellation ledger is bounded to 1,024 failed identities per Runtime boot; if repeated infrastructure failures exhaust it, new managed pauses fail with `RUNTIME_RESTART_REQUIRED`. Resolve the transport/storage fault, confirm that no update or recovery is pending, then restart only Runtime through the installed Compose group. Never clear a pending recovery to remove this message.
