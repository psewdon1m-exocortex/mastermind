# Settings rollout requirements

Settings now uses the shared Backup, Updates, Wyverne Connection and Logs lifecycle. Archive and Vault mirror schedules are independent. Group updates require a downloaded, explicitly saved and reselected standard encrypted ZIP; the signed handoff and recovery protocol is described in the Updater documentation under `docs/saved-group-updates.md`.

The primary producer source trees now include the required scoped Neptune/Saturn resource reader, typed Updater enrollment/group protocol and Chronos event reader. Historical patches in `integrations/patches` remain evidence for the earlier local qualification only. Do not reapply those old patches over the new producers and do not treat their historical SHAs as identifying this implementation.

Before a release is promoted:

- Publish and qualify the actual producer artifacts, including Updater's `mastermind.saved-copy.v2` capability and both Core releases' signed `saved_copy_protocol: 2` field. A legacy source is refused before mutation; no implicit downgrade or retained plaintext snapshot is substituted.
- Set the exact dependency versions and archive/image digests from the qualified immutable artifacts together. The existing `published: false` qualification record remains unpublished until that is done.
- Supply the existing application-scoped Kernel credentials and enrollment. Archive, mirror and reader use distinct capabilities; no second Neptune daemon is installed.
- Gryphon Connection requires the matching Gryphon stable-identity status fields and Updater's scoped Mastermind client enrollment. Qualify and publish those producer changes together; see [Gryphon and Crusher access](gryphon.md) for commands and local/live test boundaries.
- For Chronos references, resolve `services.mastermind.secrets.chronos_service_token` and `services.chronos.mastermind_reader_token` to the same Volt field, with each service permitted only its own key. Chronos resolves the expected token fresh in memory. Explicit existing file enrollment remains supported for migration.
- `services.wyvern.management_url` is an optional public, authorized HTTPS management destination resolved fresh through Kernel when clicked. It must point to an existing authorized management interface. The Wyvern daemon has no implicit standalone web admin. Without a configured destination the UI reports that configuration is required.

Restore combines service backup-policy intent and Wyvern binding intent. Both remain pending verification where their enrolled destination/binding is not confirmed. A concurrent restore cannot be acknowledged away by an older resume request. No provider credentials or resolved secret values enter these intent records.

Release qualification still requires actual signed Linux/systemd install/reuse/update/rollback and a bounded live-provider acceptance run. Local unit tests, container tests and browser fixtures are reported separately from those gates.
