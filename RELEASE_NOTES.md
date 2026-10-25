# 3.0.0 — email-only public release

- Import English parkrun result and volunteering emails through Home Assistant IMAP.
- Maintain lifetime records, calendar-year best time, rolling 12-month time/age grade,
  volunteering credits, and running/volunteering/combined venue lists.
- Seed and correct data using structured manual actions; persist across restarts.
- No parkrun API, scraping, event-directory download, remote validation or polling.
- Remove next-run selection, cancellation checks, refresh/all/new-run buttons and
  saved web-page HTML imports. Existing stored history and statistic entity IDs remain.
- HACS custom-repository support, original local brand icon, installation ZIP,
  and complete IMAP/iCloud/automation setup instructions.

## Install

Use the README's Open in HACS link, download and restart Home Assistant. Configure
IMAP and the import automation separately. For manual installation, extract
`parkrun_from_imap.zip` into the Home Assistant configuration directory.

## Existing users

Back up Home Assistant. Replace the old integration files with this version;
keep the runner config entries and local result storage. Do not install the old
and new HACS repositories together: both use the `parkrun5k` domain intentionally.
Remove old dashboard controls and refresh automations. Restart fully after upgrading.

Tests cover parsing, corrections, deduplication, migration, offline setup/reload,
rolling expiry and location lists. This release has not yet been exercised in a
live Home Assistant installation.
