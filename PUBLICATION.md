# Release maintenance

This repository starts with the email-only implementation and a new history.
No old integration commits, credentials, personal exports or profile access links
are included. Keep the existing MIT attribution. The email/check icon is an
original project asset; it is not official parkrun branding.

The integration deliberately keeps the `parkrun5k` domain so installations can
retain their existing entity IDs, services and local records. The GitHub project
and display name are Parkrun from IMAP.

## Publishing a version

1. Update `custom_components/parkrun5k/manifest.json` and `RELEASE_NOTES.md`.
2. Run the offline unit tests and syntax check locally.
3. Commit to `main` (or merge a reviewed PR). GitHub Actions runs unit tests,
   HACS validation and Hassfest.
4. After all three jobs pass, the release job creates a `v<manifest version>` tag
   and GitHub release if it does not already exist. It attaches a manual-install
   archive containing `custom_components/parkrun5k/` and installation notes.
5. HACS installs from GitHub source archives using the standard repository layout.
   The attached ZIP is for manual installation, not a remote shell installer.

An existing release is never replaced automatically. For subsequent changes, bump
the version. The workflow uses GitHub's short-lived built-in token with write
permission only in the release job. There are no stored publication credentials.
This is custom-repository HACS support, not submission to the default catalogue.

## Privacy and provenance

Runtime storage, mailbox configuration and full messages must never be committed.
Test identities and venues are fictional. Before adding fixtures, strip real
profile URLs, barcode identifiers, mailbox addresses, passwords and tokens.
Repository history is permanent once published: removing a file in a later commit
does not remove its earlier versions. If something sensitive is accidentally
committed, follow GitHub's sensitive-data removal guidance and revoke credentials
you control before considering a history rewrite.

- https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
- https://www.hacs.xyz/docs/publish/integration/
