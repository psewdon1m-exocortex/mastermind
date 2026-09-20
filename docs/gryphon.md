# Gryphon and Crusher access

Mastermind consumes the shared Gryphon gateway. Telegram bot tokens, webhooks,
user bindings and Telegram delivery belong to Gryphon, not to Mastermind.
The owner connects a registered bot and separately links their Telegram account
in **Settings → Gryphon Connection**. A private-chat `/crusher` command issues a
single-use, 30-minute code for `/crusher`; the resulting session can submit
sources and view its own progress, never read the Vault or owner settings.

## Applicable project contracts

See the vendored [system authority](policy/PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md),
[agent lifecycle](policy/PART_09_SERVICE_AGENTS_DEPLOYMENT_AND_LIFECYCLE.md) and
[Gryphon operator workflow](policy/PART_10_SERVICE_AGENTS_UI_AND_OPERATOR_WORKFLOWS.md).

| Authority | Application |
| --- | --- |
| `.docs/Part 00` | This service runbook records the implementation and verification. |
| `.docs/Part 01` and Part 10 §4 | Accent-inheriting Gryphon Connection card, distinct initialization/function/user actions, accessible overlays and explicit revoke/unlink consequences. |
| `.docs/Part 02` | Bounded audit records; no codes, credentials, message bodies or Telegram identities in logs. |
| `.docs/Part 03` | Codes, sessions and encrypted delivery replay receipts are ephemeral and excluded from service backups. Gryphon owns binding recovery. |
| `.docs/Part 04`, Part 09 | Only the scoped client socket and this service's credential directory enter Core. Updater initializes/enrolls the client. |
| `.docs/Part 05` | Existing verified shared-helper update workflow; this change does not publish a release. |
| `.docs/Part 06–07` | Owner/CSRF checks, machine authentication, bounded input, stable Telegram identity, replay, expiry, revocation, isolation and secret scans. |
| `.docs/Part 08` | N/A: every Mastermind surface remains non-indexable. |
| `.docs/Part 11` | N/A: this adds a Mastermind consumer, without changing the named initial deployment profile. |
| `.docs/Part 12` | Existing deployment/secret/agent-boundary regression gates apply. |

The user requested this integration on 2026-09-19. It adds Mastermind to the
Gryphon consumers; it does not alter Saturn's commands or authorizations.

## Commands and security

- `/crusher`: create a code and show the canonical Crusher URL separately. The
  code never enters a URL, browser history or query string.
- `/crusher_status`: show only this Telegram identity's active code/session counts.
- `/crusher_revoke`: invalidate this identity's Telegram-issued codes and sessions.
- Revoking the Telegram binding or unlinking Mastermind also invalidates its
  Telegram-issued access; owner-issued invitations are independent.

Mastermind accepts only `exocortex.telegram.command.v1` envelopes authenticated
with its Gryphon service credential. It checks the current connection and stable
private-chat user/chat IDs against Gryphon before executing or replaying a command.
An event is committed together with its code and encrypted response, so retries
after a lost response cannot issue another code. Replay receipts are bounded to
10,000 events and seven days; new work is refused if that live budget is exhausted.

## Deployment

Core uses `MASTERMIND_GRYPHON_SOCKET` and `MASTERMIND_GRYPHON_TOKEN_FILE`.
Production mounts `/run/gryphon` and the Mastermind-only credential directory;
never mount the gateway admin socket or its shared clients directory.
The exact `/internal/gryphon/command` HTTPS route is machine-authenticated;
other `/internal/` routes remain unavailable through public Nginx.

Gryphon service-status must report `connectionId` and the bound stable
`telegramUserId`/`chatId`. An older gateway reports a protocol error and cannot
issue codes until upgraded. Gateway initialization and updates require the
Updater build that recognizes Mastermind as a Gryphon consumer.

## Verification

Local qualification on 2026-09-19:

- Mastermind: complete non-root Linux suite, **620 passed**; after the final
  cleanup/protocol/replay regressions, targeted Gryphon suite **23 passed**.
- Gryphon: TypeScript typecheck/build and **21 tests passed**, including
  isolation of Mastermind and Saturn bindings on one bot.
- Updater: component suite and targeted API tests for Gryphon initialization,
  scoped enrollment, head boundaries and helper updates passed. The broader API
  suite hit an unrelated existing spool test's HTTP 507 free-space guard; this
  is not reported as a passing full Updater suite.
- Python CI lint (`src`, `tests`), new Python fixture scripts and standalone
  repository/documentation validation passed. An additional lint run over all
  legacy scripts reports existing findings outside this change.
- Real Gryphon SQLite/client UDS + real Mastermind HTTP + Chromium: GUI function
  selection, private-account link, one-use code, duplicated delivery, foreign
  user rejection, guest Crusher unlock, source-file upload and acceptance,
  owner isolation, status, scoped revoke,
  binding revoke, keyboard focus during refresh and mobile layout passed.
- Gitleaks source scans of Mastermind, Gryphon and Updater: **no leaks found**.

The Telegram transport and Kernel origin resolver are controlled fixtures;
actual external Telegram delivery and production Linux/systemd deployment are
separate acceptance steps. No provider token, live bot or real chat is used in
this qualification. Mastermind's main local GUI is updated at port 18390; its
Gryphon connection stays unconfigured until real enrollment and bot selection.

To repeat the bounded integration test, build the local sibling Gryphon with
`pnpm build`, build Core (`docker build -t mastermind-core:development .`), then
run `python scripts/qualify_gryphon.py`. Node/Playwright with Chromium and Docker
must be available. `--core-image` and `--gryphon` select other local candidates.
Ports 18496/18497 must be free. The runner creates isolated source copies and
synthetic credentials, stops its containers and removes its credential files
on exit. Screenshots go to ignored `artifacts/gryphon/`.
The synthetic Vault is retained under ignored `.local/mastermind-gryphon-*`.
The upload is a small text file; the existing acceptance policy still checks
for at least 8 GiB of available processing space without allocating or copying
that amount. AI processing and source quality are outside this access test.

The producer changes reside in the sibling **gryphon** and **updater** source
trees. They must ship together with this consumer before a production rollout;
older published artifacts do not gain these capabilities from a Core update.
Live Telegram verification additionally requires a selected bot and authorized
personal test chat. Bot tokens are entered through Gryphon management only.
