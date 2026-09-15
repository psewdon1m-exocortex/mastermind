# Sharing

A Share grants access to one path-bound note projection. It uses a high-entropy capability with a stored HMAC, optional password, expiry and explicit revocation, following Saturn's public sharing semantics. Owner management is authenticated; public capability possession never grants owner, Runtime, resource-reader or Crusher privileges.

Paths intentionally determine identity. Rename/move follows the managed path change. After deleting a note and creating another note at the same path, an existing Share can become readable again; this is an accepted product decision. Revoking the Share prevents that revival. This behavior must be considered before reusing paths for different content.

## Safe view and editing

The public view is a restricted Markdown projection. It does not resolve `@` references, native wikilinks, embeds, external URLs or internal/attachment resources. Sanitization applies on the server to both saved public text and rendered content; removing a few visible characters in the browser is not the authorization boundary. HTML, encoded links and alternate Markdown syntaxes cannot obtain resource grants.

An editable Share is still scoped to that one note. It uses the issued edit capability, CSRF/origin checks and the current ETag. A stale save receives a conflict after native buffers have been flushed; it never overwrites a later owner edit. Public writes do not count as owner Activity. Note/source bodies and passwords are omitted from audit output.

All shared pages and APIs are no-store/non-indexable. Share tokens do not appear in referrer headers, navigation collections, sitemaps or unredacted Nginx access paths. Noindex does not replace capability checks. Invalid, expired, wrong-password and revoked capabilities are qualified independently in [tests](../tests/test_shared.py) and the browser evidence recorded in [IMPLEMENTATION](IMPLEMENTATION.md).
