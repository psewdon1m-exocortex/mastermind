# Crusher

Crusher accepts a source and displays its durable pipeline stage and progress. It does not display the generated note, candidate text, placement context or result previews on the Crusher page. The completed note belongs in Vault. Owner access and public submission capabilities are distinct.

## Sources and isolation

Supported sources include text, bounded uploads, public web pages, YouTube/video/audio and supported documents/archives, Git repositories and owner-only Saturn resources read through Neptune. PDF/OCR, DOC via antiword, DOCX, RTF, XLSX cached values, PPTX and EPUB extraction runs in the dedicated Worker. Spreadsheet formulas and Git hooks/scripts are never evaluated. Git helpers and arbitrary commands are not accepted from a source.

Worker receives only the current source and bounded chunks. It has no Vault mount, database, provider/agent credentials belonging to other principals or commit API. Extractors run through the Linux sandbox and allowlisted binaries; browser requests and redirects undergo public-address checks. The offline multilingual E5 model is pinned by digest, uses at most 512 tokens/chunk and never downloads model artifacts at runtime.

The Worker browser is the separately pinned official stable Chrome for Testing **153.0.8010.36**, recorded with download URL and SHA-256 in `worker-browser.lock.json`. The build verifies and installs those bytes and uses Playwright only as the controller. It does not install the older browser bundled with Playwright. The executable still enters the same Landlock/seccomp wrapper; all network requests pass through the bounded parent broker. Full image CI checks the actual browser version, executes a JavaScript-generated article and rejects its attempted request to loopback. The initial switch addresses the vulnerable Chromium 151 baseline; only a fresh scan of the resulting exact image can establish its new vulnerability status.

## Context and placement

The provider does not receive the whole Vault. Placement follows root → `#main` → `#key`, including nested key branches, with selected bounded candidate text. Maximum hierarchy depth is 8; limits are 12,000 unique / 24,000 transmitted context tokens per job, with the source/model budgets in the final requirements. Ambiguous placement falls back to Inbox. Source text is untrusted data, not authority to read secrets or execute instructions.

Structured output is validated before a single canonical commit. Stable job/commit identities and durable transitions prevent a retry after a crash from creating a second note. Retryable stages have bounded attempts/deadlines; an invalid provider schema eventually fails. A missing source after recovery is explicit failure, not fabricated success.

## Public access and bounds

Owner issues a short-lived one-time six-digit activation code. Activation creates a scoped public submission session. Public callers can submit and inspect sanitized progress for their own jobs, and can use a separately scoped status ticket where supported. They cannot read results, list the Vault, fetch private Saturn sources or access owner APIs. Expiry during an already accepted job does not cancel its durable work.

Default bounds: 1 MiB raw text, 2 GiB source, two concurrent source uploads, 16 GiB incoming/work quota, one active job, queue 100 globally / 20 per public session. Source archive expansion is at most 8 GiB, 10,000 members and depth 16. Fetch/clone is bounded to 15 minutes, extraction to 20 minutes, a provider attempt to 5 minutes and the accepted job to 60 minutes. Successful temporary data are removed promptly; failed sources expire within 24 hours.

The Google provider key and approved model names resolve through Kernel/Volt. Qualification records explicitly distinguish an actual paid provider call from a controlled REST fixture. Neither fixture output nor a mock service proves live provider availability.
