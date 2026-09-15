# Compatibility and decisions

The initial candidate pins Obsidian 1.13.7, KasmVNC 1.5.0 and the multilingual E5 artifact in [embedding-model.lock.json](../embedding-model.lock.json). Python/Worker dependencies and the TypeScript toolchain are locked. Core, Runtime, Worker, Bridge, DB schema and local model form one signed compatibility group.

The neighboring baseline versions are Kernel 0.2.10, Volt 0.1.5, Saturn 0.1.15, Chronos 0.1.1, Neptune 0.1.7 and Updater 0.4.7. **Unmodified upstream releases are not sufficient for every new Mastermind contract.** [compatibility.json](compatibility.json) names the exact baseline source SHAs, exported patches and patch hashes used for local qualification. These changes are unpublished candidates; do not label them released producer versions.

| Producer | Required local change |
| --- | --- |
| Saturn | Independent typed reader scope, bounded content/Range, durable operation-lock recovery and transport bounds |
| Neptune | Scoped reader through discovery/Saturn, complete zip-tree mirror, exact streaming receipts, path/cancellation/large-transfer validation |
| Updater | Own-head three-image group, pre-pull preparation, sealed streaming backup spool, functional rollback and typed enrollment |
| Chronos | Bounded exact service credential consumption for the scoped card reader |

The patches are reviewable under `integrations/patches`. Apply them only to the pinned clean producer revisions, run their own checks and the consumer integration suite, then release the producer changes before a public Mastermind release claims that dependency tuple. No direct Saturn fallback or second host Neptune daemon substitutes for the missing contracts.

## Closed product decisions

Vault inherits Obsidian UI/UX; the Shell follows project rules. Native rename updates wikilinks. One Mastermind enrollment creates independent archive and mirror pipelines plus a distinct reader. Plugin configuration/secrets remain opaque. The approximately 350 MiB representative dataset is a qualification input. Shares suppress all external/internal resource links, are non-indexable, follow Saturn capability semantics and intentionally revive when a path is reused. Crusher displays input/progress only and places output using bounded root/main/key hierarchy context. Other unspecified decisions use the recommendations in the accepted final requirements.

## Release and deployment evidence

[IMPLEMENTATION](IMPLEMENTATION.md) is the stage/evidence ledger. It distinguishes actual service/host/browser tests from protocol units and controlled provider/transport fixtures. Production DNS/certificates, paid provider credentials and a published producer/release tuple require their own real observations. Those checks must remain NOT_RUN where no such observation exists.

The central policy snapshot includes the user's pre-existing Part 12 working-tree change. The exact effective bytes are pinned locally. Publication additionally requires an immutable central catalog revision containing those effective rules; an older central SHA must not be misrepresented as containing the changed catalog. The original central checkout is preserved.
