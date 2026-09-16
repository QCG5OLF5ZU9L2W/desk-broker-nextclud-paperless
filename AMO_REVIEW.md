# Paperless Send 2.4.12 — unlisted signing and source review

This release is intended for private self-distribution (the **unlisted** channel).
It has not been submitted or approved by Mozilla in this build session.

## Change in 2.4.12: editable series assignment inheritance

The only runtime changes from 2.4.11 are app.html, app.js, background.js and the
manifest version. The existing native multipage preview, CSP, permissions and
extension ID are unchanged. No third-party code, generated executable payload,
minification, bundling or new transmission destination is introduced.

The composer offers a default-on “Letzte Zuordnung übernehmen” checkbox within
series mode. It keeps the previous accepted submission's tags, correspondent,
document type, storage path ID, custom values, document date and completed-tagging
flag editable for the next PDF. The title remains document-specific. A new
composer window in the same unlocked session can restore that classification.
The series template excludes sharing, local deletion and Deck actions.

background.js holds one deep-copied, validated assignment and two booleans only in
memory. A rejected start does not replace it. Locking, reauthentication and target
changes reset it; it is not written to local or session storage. Existing optional
title and assignment histories are separate and unchanged. Catalog validation
skips removed fields, and delayed restore cannot replace manual input or an
explicitly selected profile. Disabling inheritance clears classification only
when moving to the next PDF, retaining the existing document-date behavior.

## Correction after the reviews of 2.4.9 and 2.4.10

Both notices cited obfuscated code without identifying a file or line. Comparison
with the user-supplied, reportedly approved 2.4.7 package isolated the bundled
PDF renderer as the main new source-review concern. Reformatting our own code
in 2.4.10 had left every upstream renderer file unchanged.

In 2.4.11, **the entire bundled PDF.js distribution is removed**: both modules,
workers, WebAssembly binaries, compiled JavaScript decoder fallbacks, fonts,
character maps and other renderer assets. The old distribution archive, source
subset, vendor lock and verification script are also removed from this source
package. No equivalent encoded payload or remote renderer replaces them.

The multipage hover preview is retained. Readable first-party `pdf-preview.js`
passes a validated PDF Blob to Firefox's built-in PDF viewer in an iframe.
Mouse wheel and arrow keys change the ordinary PDF URL fragment (`page`, `zoom`),
without accessing the viewer's privileged DOM or internal API. A changing
fragment restores the correct page position when a hidden preview reopens.
`background.js` reads the document's `page_count` from Paperless for page limits.
If that optional field is unavailable, the native viewer still displays its own
page counter and supports navigation.

The iframe has `sandbox="allow-scripts"`, no same-origin grant and no permission
for forms, popups, downloads or top navigation. It is passive and outside the Tab
sequence. PDF parsing and the viewer's own document handling are provided by
Firefox, not shipped add-on code. The add-on does not change Firefox preferences.

PDF bytes are fetched with the existing authenticated, read-only Paperless API
path, bounded to 100 MiB and checked for a PDF signature. The frame receives only
a local Blob URL; credentials are not put in URLs or passed to the viewer. Up to
three PDF Blobs are cached in the open UI's memory. Session/server changes,
locking, eviction and window closing clear frames and revoke their Blob URLs.
Hover does not upload a document or create a public link.

The runtime CSP is now:

```
script-src 'self'; object-src 'none'; frame-src blob:; base-uri 'none';
```

There is no WebAssembly exception, JavaScript eval, dynamically imported code,
minifier, bundler or executable third-party library in the XPI. The existing
base64 decoding in `background.js` converts PDF bytes received from the optional
native helper; it does not decode executable code. Icons are PNG images.

The add-on ID, permissions, desktop minimum version and existing document
workflows remain unchanged. Version 2.4.12 is read by both the tab title and the
sidebar from the manifest. The source package's historical release notes describe
older releases and are not the current runtime architecture.

## Reproduce the unsigned XPI offline

Requirements: Python 3.9 or newer, standard library only. Tested with Python
3.12.14 on Linux. No npm, compiler, formatter, browser, network, credentials or
native helper installation is needed to build.

From the extracted package directory:

```sh
python3 build.py
```

Output: `dist/Paperless-Send-2.4.12-unsigned.xpi`.
Every file in `extension/` is copied unchanged in sorted order with fixed ZIP
timestamps and file modes. These readable files are the exact runtime sources.
The included XPI is a reference output, not a build input. No test code, fixture,
review report or optional native helper is included in the XPI. Mozilla signing
will add signature files, which are not produced by this build.

## Review and validation

See `TESTRESULTS.md` and `validation/`. The standard Mozilla addons-linter 10.11.0
scan (no suppressed rules) finds zero errors, zero notices, no unknown minified
files and no JavaScript libraries. The one remaining warning is the pre-existing
Android minimum-version/data-consent-key compatibility warning. Desktop Firefox
is the target tested here. No Android compatibility or manual Mozilla approval
is claimed.

145 Node tests pass, including accepted-versus-rejected submissions, mutable
values, false/zero/monetary/document-link custom values, cleared assignments,
explicit profile precedence, delayed catalogs and session changes. The new
series-browser.cjs test runs the actual composer in Firefox 153: queued PDFs,
editable inherited values, the latest assignment in a newly opened window,
opt-out and synchronized calendar dates, with no console errors. Its API and file
adapters are fixtures, and no user document is uploaded. The unchanged native
preview was tested in 2.4.11; those prior results are labeled in TESTRESULTS.md.

Optional browser-test dependency: Playwright 1.62.1 with Firefox. The test driver's
browser preferences and fixtures are not included in the XPI. The offline release
build needs only Python's standard library.

## Manual review steps

Series-mode check: select multiple PDFs, enable series mode, keep inheritance
checked and assign tags/types/custom fields. Send the first PDF and confirm the
next retains those values with an empty title. Edit a value, send again, then open
a new send window; the edited value should be present. Lock and unlock the session;
a new window must not restore the previous session's template. A profile chosen
explicitly during launch should take priority over automatic inheritance.

Unchanged preview behavior:

1. Configure a test Paperless-ngx instance and unlock the add-on session.
2. In Firefox's PDF application settings choose **Open in Firefox**.
3. Hover a completed job's thumbnail, or an existing duplicate's document name.
4. Keep the pointer there and use the mouse wheel, arrow keys or Page Up/Down.
5. Leave or press Escape; reenter and confirm the selected page reappears.
6. Lock the session and confirm that the document preview disappears.

With Firefox's PDF viewer disabled, the existing thumbnail remains and a hint is
shown. If Firefox cannot load the embedded viewer, the thumbnail remains with a
hint after the load timeout. The extension does not enable the viewer or change
application preferences itself.

## Private submission

Upload the unsigned XPI as a new version of the existing add-on using the
**self-distribution / unlisted** channel. Attach this matching package as source
if requested, and copy the notes below into “Notes for Reviewers”. Download and
install Mozilla's signed XPI once signing succeeds. This package does not include
signing credentials, a public listing or a configured self-hosted update server.

Unlisted extensions still require signing for ordinary Firefox Release/Beta and
remain subject to the same source rules:

- https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/
- https://extensionworkshop.com/documentation/publish/source-code-submission/
- https://extensionworkshop.com/documentation/publish/add-on-policies/

## Notes for Reviewers — ready to paste

This is an unlisted update for private self-distribution of Paperless Send.
Version 2.4.12 adds editable assignment inheritance in series mode using only
readable first-party JavaScript. One validated assignment is kept in memory for
the current login and cleared on lock, login or target change. No new permissions,
third-party code or network destination is introduced. The native preview from
2.4.11 remains unchanged. Run python3 build.py for a byte-identical unsigned XPI.
Following the source-review rejections of 2.4.9 and 2.4.10, we removed the entire
bundled PDF.js renderer, including its compiled JavaScript and WASM decoders.
No third-party executable library remains in the XPI and no remote replacement
is loaded. Readable first-party code now embeds validated PDF bytes in Firefox's
own built-in viewer and uses ordinary URL fragments for hover page navigation.
The iframe is sandboxed and does not receive extension-origin privileges.
The wasm-unsafe-eval CSP exception has been removed. All runtime sources are
included unchanged in extension/. Run python3 build.py to reproduce the unsigned
XPI offline with Python's standard library. AMO_REVIEW.md and TESTRESULTS.md
describe current series-mode validation and the earlier installed-extension
preview test. The notices did not specify an offending file, so this is a concrete source
change for renewed review, not an assertion that the earlier decisions were wrong.
