# Mastermind Bridge

Mastermind Bridge adds Mastermind `@` references to Obsidian and connects the
managed Obsidian runtime to Core. Its source lives in this repository's `bridge/`
directory. Standalone downloads use a separate **prerelease** channel; they do
not install or update the Mastermind service.

## Install a standalone preview

1. Download `mastermind-bridge-<version>.zip` from a `bridge-v<version>` release.
   GitHub's automatic **Source code** archives are source checkouts, not plugin packages.
2. Verify the download against the attached `SHA256SUMS` if desired. For example,
   use `Get-FileHash <zip> -Algorithm SHA256` on Windows or `shasum -a 256 <zip>` on macOS.
3. Extract the `mastermind-bridge` folder into your Vault's `.obsidian/plugins/`.
   The resulting folder contains `main.js`, `manifest.json` and `styles.css`.
4. Enable community plugins and **Mastermind Bridge** in Obsidian settings.
   Reload Obsidian after replacing an existing installation.

The same three files are also attached individually. Install only these plugin
files in the Vault. Preserve an existing `portable-history.json` when updating;
generic release packages never contain anyone's notes, credentials or history.

## Current scope

- Desktop only. Automated package builds do not qualify Windows/macOS Obsidian UI behavior.
- Native `@` integration with Graph, Local graph, Backlinks and Outgoing links is
  qualified on **Obsidian 1.13.7** and disabled on other versions. The current
  manifest's `minAppVersion` is a loading floor, not a promise that graph hooks
  work on every later Obsidian release.
- Without managed runtime configuration, Bridge starts in portable mode using
  local notes and reference history. A new installation has no history of
  previously deleted or renamed notes; exported Vaults may carry that history.
- The Related notes sidebar uses the managed Core's context-indexing search and
  follows the editor buffer while you write. It is unavailable in portable mode.
- Chronos/Saturn nodes remain available to the reference integration. Live
  external cards require the managed service connection. Standalone remote
  enrollment and synchronization back to Mastermind are not implemented.
- Managed installations use the Bridge bundled with their matching Core release.
  Do not use these standalone downloads to update a managed runtime independently.

See [Bridge architecture and behavior](../docs/mastermind-bridge.md) for details.
Community Plugins directory submission and licensing decisions are separate from
this initial download workflow. These prereleases are for manual installation.

## Build and release

From the repository root, with the Node/Python versions pinned in the workflow:

```sh
npm --prefix bridge ci
npm --prefix bridge run check
npm --prefix bridge test
npm --prefix bridge run build
python -m unittest discover -s bridge/tests -p 'test_release.py' -v
python scripts/bridge_release.py package --folder artifacts/bridge-preview --revision <full-source-commit-sha>
```

Use an empty output directory. For release evidence, use a clean checkout of the
named commit; packaging a working tree locally is only a preview of those bytes.
The packager checks the shared service/Bridge versions, build hashes and archive
contents, then writes deterministic files and source metadata. It never publishes.

The [Bridge workflow](../.github/workflows/bridge.yml) runs on pull requests, `main`
pushes and manual dispatch. Each run retains a downloadable package artifact for
30 days. These ordinary runs have read-only repository permissions.

After merging and checking the intended source commit on `main`, create and push
an immutable `bridge-v<manifest-version>` tag (for example `bridge-v0.1.0`). The
same workflow builds and scans the package, then a separate job publishes the
verified bytes using its short-lived `GITHUB_TOKEN`. No new personal token,
signing secret or self-hosted runner is required. Repository Actions policy must
allow that tag job `contents: write`; restrict creation/deletion of `bridge-v*`
tags to release maintainers through repository rulesets.

Publication starts as a draft, checks GitHub's uploaded SHA-256 digests and only
then opens a prerelease with `make_latest=false`. Failed uploads leave a draft;
rerun the failed workflow to finish uploading missing files. A retry refuses
changed or unexpected files and never overwrites an already published release.
If bytes must change, update the shared service/Bridge version and use a new tag.

Published assets are exactly:

- `main.js`, `manifest.json`, `styles.css`;
- `mastermind-bridge-<version>.zip` containing the same three files;
- `bridge-release.json` recording source, version, compatibility and file hashes;
- `SHA256SUMS` covering all five other assets.

The JSON metadata and checksums describe content integrity; they are not a
cryptographic signature or whole-service qualification. No claim of a desktop
UI test is added by this packaging workflow. Core/Runtime/Worker publication
continues through the protected `mastermind-v*` release pipeline described in
[releases and updates](../docs/releases.md).
