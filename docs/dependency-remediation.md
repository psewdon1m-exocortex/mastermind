# Dependency remediation for the local 0.1.0 candidate

Status: **REVIEW_REQUIRED**. Functional qualification passes do not close the
release security gate. No finding has been suppressed or accepted as risk.
This is a remediation record, not an allow-list or a VEX approval.

The 2026-09-15 exact-image scan is retained at
`artifacts/supply-chain/20260915T145209Z-5e2e5a61/`. Syft 1.51.1 and Grype
0.118.0 scanned the immutable Core/Runtime/Worker identities recorded by local CI.
Raw High/Critical package matches are respectively **51/0**, **70/2** and **71/9**;
these counts include repeated source-package matches and possible version errors.
The final 6e11a0f rebuild has different OCI provenance indexes but identical
RootFS layers and runtime configuration (`artifacts/final-image-payload-equivalence.json`).
Its new read-only inventory also passed (`artifacts/security-inventory-6e11a0f.json`).
The original scan remains attached to its original image identities; no new scan
PASS or remediated finding is inferred from this equivalence check.

## Completed changes and evidence

The candidate uses Debian 13 security updates, Python 3.12.14 and pinned Chrome
for Testing 153.0.8010.36. Build-only Runtime curl and unused Worker FFmpeg/Xvfb
were removed. Actual extractor, browser JavaScript/SSRF, model, native Runtime
and related-service tests pass. These changes reduced findings but did not
produce a passing final scan.

`scripts/security_inventory.py` collects read-only facts from exact images,
without credentials, network, writes or added capabilities. The executed inventory
is `artifacts/security-inventory-b42891f.json`. It found:

- Python 3.12.14 with bundled Expat 2.8.3 in every image; Runtime additionally
  contains Debian Python 3.13.5. Shared Expat updates alone cannot repair the
  bundled interpreter copy.
- No cupsd, tiffcrop, getfacl, setfacl, chacl or Python libxml2 binding. infocmp,
  mount and nsenter are present. Archive::Tar is absent in Core and present in
  Runtime/Worker.
- ELF scans of 757/1196/985 files completed without parser errors. No imports of
  strfmon/strfmon_l or the deprecated DNS diagnostic functions were found.
  gzwrite imports do exist, including libxml2 in Runtime/Worker.

These observations are narrower than proof of non-reachability: dynamic plugins,
FFI and indirect use need separate consideration. In particular, absence of an
ELF import is not a general security exemption.

## Remediation order

| Area | Required work before closing the finding |
| --- | --- |
| Expat | Adopt and qualify 2.8.4 fixes for shared libraries **and** Python's bundled parser. CVE-2026-66046 concerns quadratic attribute processing without special parser flags; entity-only protections are insufficient. Validate malformed XML/resource limits and real document extraction. |
| libxml2 | Debian's version prefix 2.12.7 actually ships 2.9.14. Resolve CVE-2026-6653 and 86140 while retaining the ABI needed by Runtime/Worker dependencies, then repeat native SVG/windowing and browser/extractor tests. |
| Worker Git/libcurl | Replace the affected retained libcurl package with a maintained compatible build, or complete individual authoritative applicability reviews of every finding against Git's actual configured call paths. Sandbox isolation alone is insufficient. |
| Runtime Debian Python | Resolve its separately installed interpreter findings; the application Python version does not cover it. Determine and test the exact Openbox/Kasm dependency before changing package installation. |
| Source-package/tool matches | Review cupsd, tiffcrop, Python SAX binding, ACL/util-linux, glibc, JXL, Perl, ncurses and zlib individually against exact-image presence, invocation and relevant privilege/API conditions. |
| Python version database | Official Python 3.12.14 release notes include fixes for CVE-2026-3644, 4224 and 7210. Record that evidence per actual image/package without extending it to Debian Python or later Expat issues. |

Primary references: [Debian Expat tracker](https://security-tracker.debian.org/tracker/source-package/expat),
[libxml2 CVE-2026-6653](https://security-tracker.debian.org/tracker/CVE-2026-6653),
[libxml2 CVE-2026-86140](https://security-tracker.debian.org/tracker/CVE-2026-86140),
[official curl releases](https://curl.se/download.html), and
[Python 3.12.14 release](https://www.python.org/downloads/release/python-31214/).

The official libxml2 fix `463bbeeca1805b5c4828f50d0fefc4eebaf620df` was inspected:
it changes entity accounting, parser structures and multiple code paths. Copying
it into the older distro package is not a qualified one-line fix. The separately
inspected bounds-check commit is `d1686f91dbda141a752200419d35639fd6b38340`.
Neither prototype patch was installed into shipped images or presented as fixed.

After actual remediation, rebuild once, rerun the affected functional tests,
generate fresh SBOMs and scan the exact new images. Preserve original findings
and verified provenance for any backport. An exception needs owner, reason,
expiry and an explicit material decision under central Part 07; no such decision
is assumed. `release_candidate.py` continues rejecting unresolved High/Critical
findings, unpublished producer patches and an uncommitted effective policy.
