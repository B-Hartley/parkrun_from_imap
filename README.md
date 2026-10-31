# Parkrun from IMAP

A local Home Assistant integration for your parkrun results and volunteering.
It reads messages passed to it by Home Assistant's **IMAP integration**, or data
you enter manually. It does not contact parkrun servers, download event directories,
scrape pages, emulate an app, or require parkrun credentials.

This is an independent community project, not an official parkrun integration.
The icon is an original email symbol, not parkrun branding.

## Install via HACS or Marketplace

Depending on your Home Assistant version, the integration store may be labelled
**HACS** or **Marketplace**. Use the instructions that match your interface.
This project is a **custom repository**, not a default catalogue listing.

### HACS (installations showing HACS)

1. Install [HACS](https://www.hacs.xyz/docs/use/download/download/) if needed.
2. Open [Parkrun from IMAP in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=B-Hartley&repository=parkrun_from_imap&category=integration), or open **HACS → ⋮ → Custom repositories**.
3. Add `https://github.com/B-Hartley/parkrun_from_imap` with category **Integration**.
4. Find **Parkrun from IMAP** and select **Download**.
5. **Restart Home Assistant** to load the new Python code.

### Marketplace (installations showing Marketplace)

1. Open **Marketplace** in Home Assistant.
2. Find the **Custom repositories** / **Add repository** option (the wording and menu position can vary by version).
3. Add `https://github.com/B-Hartley/parkrun_from_imap` as an **Integration** repository.
4. Find **Parkrun from IMAP**, then select **Install** or **Download**.
5. **Restart Home Assistant** after installation or code updates.

### Finish setup (both methods)

1. Open **Settings → Devices & services → Add integration → Parkrun from IMAP**.
2. Enter your numeric athlete barcode (an optional `A` prefix is accepted) and display name.
3. Repeat for additional runners, if needed.
4. Set up the separate IMAP integration and email automation as described below.

Requires **Home Assistant 2026.3 or newer**. Do not install the old Parkrun5k
repository alongside this one. When migrating from an older repository, back up
Home Assistant first and preserve existing runner entries and stored data.

For manual installation, download `parkrun_from_imap.zip` from the latest release
and extract it into your Home Assistant configuration directory, or copy
`custom_components/parkrun5k` into `config/custom_components/parkrun5k`.
Replace old files instead of overlaying them, then restart Home Assistant.
The mailbox and automation below are separate setup steps.

## Configure the mailbox

Add Home Assistant's built-in **IMAP** integration under **Settings → Devices &
services**. The mailbox credentials belong in IMAP, never in this integration or
the automation YAML. A dedicated folder for incoming parkrun emails makes it
easier to manage old messages. `INBOX` also works.

For **iCloud Mail**, use:

| Setting | Value |
| --- | --- |
| Server | `imap.mail.me.com` |
| Port | `993` |
| Security | SSL/TLS enabled |
| Username | Your iCloud Mail username; try the full email address if needed |
| Password | An Apple app-specific password |
| Folder | `INBOX`, or the exact folder you want to monitor |

Create a separate mailbox folder called **Parkrun Processed**. The automation
moves messages there only after their data has been saved successfully.

In IMAP's options, set the **search** to this single line:

```text
FROM "noreply@parkrun.com" OR SUBJECT "Your result from" SUBJECT "Thank you for volunteering at"
```

The two subject searches are alternatives; the sender restriction applies to both.
Do not use `UNSEEN`: a message should still import if you read it first.
To restrict old mail, append `SINCE 01-Oct-2026`, choosing your own starting date.
A date restriction excludes older volunteering acknowledgements too.

For tests forwarded from your own address, temporarily use:

```text
OR SUBJECT "Your result from" SUBJECT "Thank you for volunteering at"
```

The importer still checks the athlete barcode in the message body. Restore the
sender filter after testing. Forward a real complete message, retaining its links
and original subject text; `Fwd:` prefixes are accepted.

Leave the custom event template empty. Event body text/headers can remain off:
the automation uses `imap.fetch` for the full body, avoiding the event text limit.
IMAP Push can be used if it works with your provider; if arrivals are unreliable,
turn Push off and test normal polling. Parkrun5k itself does no polling.

## Connect incoming email to the importer

In **Developer Tools → Events**, listen for `imap_content`, then reload the IMAP
entry or send a matching message. Copy its **`entry_id`**. This is the IMAP config
entry ID, not its sensor entity ID and not the Parkrun5k entry ID.

Create an automation in YAML mode using the example below. Replace
`YOUR_IMAP_ENTRY_ID` and `1234567` with your entry ID and athlete barcode. Create
`Parkrun Processed` in the mailbox first, or remove the final move action while testing.

```yaml
alias: Import parkrun emails
mode: queued
max: 50
triggers:
  - trigger: event
    event_type: imap_content
    event_data:
      entry_id: YOUR_IMAP_ENTRY_ID
      initial: true
conditions:
  - condition: template
    value_template: >-
      {{ 'Your result from ' in trigger.event.data.get('subject', '')
         or 'Thank you for volunteering at ' in trigger.event.data.get('subject', '') }}
actions:
  - action: imap.fetch
    data:
      entry: "{{ trigger.event.data.entry_id }}"
      uid: "{{ trigger.event.data.uid }}"
    response_variable: result_email
  - action: parkrun5k.import_email
    data:
      athlete_id: "1234567"
      subject: "{{ result_email.subject }}"
      body: "{{ result_email.text }}"
  - action: imap.move
    data:
      entry: "{{ trigger.event.data.entry_id }}"
      uid: "{{ trigger.event.data.uid }}"
      target_folder: Parkrun Processed
```

Do not enable `continue_on_error` on the import action. A parsing or save failure
must stop the move, leaving the message available to investigate/retry. If the
move fails after a successful import, reimporting the same message is safe.

For several runners, use separate filtered folders/IMAP entries and one automation
per runner. Do not point identical automations for different athletes at one
unfiltered mailbox: each importer deliberately rejects other people's barcodes.

`initial: true` is an IMAP message-change flag, not “only at startup”. IMAP is not
a bulk-history importer: changing a filter or reloading can expose an existing
matching message but does not guarantee every old email will be emitted. Use
manual imports below to backfill, or present old emails individually to a test
folder. Keep processed messages outside the watched folder.

## What is maintained

| Sensor | Meaning |
| --- | --- |
| Total Runs, Latest Run, Category, Latest Milestone | Latest reported running total and available result details |
| Personal Best, Best Age Grade | Best-known lifetime records, with date/location when known |
| Best Time This Year | Best-known time in the current calendar year |
| Best Time Last 12 Months, Best Age Grade Last 12 Months | Best dated performances in the rolling window, with achievement date and venue |
| Volunteer Count | Latest reported volunteering milestone credits, not number of roles |
| Unique Locations | Distinct running venues; retains its original entity ID |
| Volunteer Locations | Known venues where you volunteered |
| Visited Locations | Running and volunteering venues combined, counting each venue once |

All location sensors expose `locations` and `location_details`. New activity emails
extend the lists. Volunteer details distinguish known imported occasions from an
email's reported lifetime occasions at that venue. First/last *known* dates are not
claimed to be first-ever dates when older activity is missing. Names compare
case-insensitively, ignoring a trailing “parkrun” and treating “&” as “and”.

Partial history is labelled with `history_complete: false`. A lifetime count in
one email does not reveal all the venues or dates behind that count. New volunteer
and combined-location sensors count known venues. A seeded numeric running-venue
total remains available even when the names of all those venues are not yet known.
Unknown statistics stay unknown until evidence or manual data supplies them.

Run and volunteering emails are stored separately, deduplicated by activity
identity. Older emails do not roll back a newer dated reported total. A corrected
latest email may correct its total. Existing undated volunteer totals act as a
floor until dated reports catch up; correct a bad floor with `update_data`.
Volunteering emails do not identify roles, so existing role information is retained
but new roles are not guessed.

Lifetime records improve automatically. Venue PB/year-best values in result emails
can improve the lifetime PB, but cannot supply a missing achievement date. Rolling
records require actual dated performances and expire at local midnight; they cover
after the same calendar date last year through today (Feb 29 uses Feb 28 as the
previous-year boundary). Equal performances use the most recent achievement.

## Manual imports and setup

Only two actions are exposed: **`parkrun5k.import_email`** and
**`parkrun5k.update_data`**. Both validate inputs before saving. Changes survive
restarts. Omitted fields stay unchanged.

To import an old or forwarded email directly, use **Developer Tools → Actions**:

```yaml
action: parkrun5k.import_email
data:
  athlete_id: "1234567"
  subject: "PASTE THE COMPLETE ORIGINAL SUBJECT HERE"
  body: |
    PASTE THE COMPLETE EMAIL BODY INCLUDING LINKS HERE
```

English result and volunteering acknowledgement formats are supported. The full
body must contain the matching barcode in a profile link or other supported barcode
reference. The importer never follows links. Names alone cannot verify identity.
If the plain-text part omits links, use the complete HTML body (for example the
appropriate part fetched with IMAP's `imap.fetch_part`) instead. Do not paste the
all-results web page: this version has no web-page importer.

To seed or correct records, use a structured update with fictional example values:

```yaml
action: parkrun5k.update_data
data:
  athlete_id: "1234567"
  updates:
    summary:
      total_runs: 100
      volunteer_count: 12
      latest_category: VM45-49
      year_best: "24:10"
      year_best_year: 2026
    personal_best:
      time: "23:15"
      date: "2025-05-10"
      location: Example Park
    best_age_grade:
      value: 63.5
      date: "2025-05-10"
      location: Example Park
    results:
      - date: "2026-04-11"
        location: Example Park
        time: "24:10"
        age_grade: 61.8
    locations:
      run:
        - Example Park
        - Riverside
      volunteer:
        - Example Park
```

Explicit PB and age-grade updates may correct records in either direction. A new
value clears old provenance unless supplied in the same call. Dated results seed
rolling statistics and venue lists; they do not invent run counts or replace the
Latest Run sensor. Supply `summary.total_runs` when needed. At most 1,000 dated
results can be submitted per call; larger histories can be split into batches.

`locations.run` and `locations.volunteer` replace their respective manually seeded
name lists. Actual activity records continue to contribute venues. A name list
does not establish a complete dated history.

To exclude mistaken dated evidence from rolling records and venue calculations:

```yaml
action: parkrun5k.update_data
data:
  athlete_id: "1234567"
  updates:
    remove_results:
      - date: "2026-04-11"
        location: Example Park
```

A later explicit result or matching result email can restore that evidence.
All-time records are conservative: correct them explicitly if a mistaken run
previously established a record. Older flat fields are also accepted, but do not
mix them with `updates`: `personal_best`, `pb_date`, `pb_location`, `pb_event_id`,
`best_age_grade`, `bag_date`, `bag_location`, `bag_event_id`, `total_runs`,
`unique_locations`, `volunteer_count`, `latest_category`, `year_best`,
`year_best_year`. Supply the two yearly fields together.

## Move from the old Parkrun5k repository

The internal integration domain remains `parkrun5k` to preserve existing IDs,
storage and action names. Do not install both repositories simultaneously. Remove
the old repository from HACS management first, then add this one; keep your runner
config entries and stored data. If an uninstall removes the files, install the new
version before restarting. Take a Home Assistant backup first.

## Upgrade from 2.x

Back up Home Assistant, install 3.x, and restart it fully. Keep the existing runner
entries: their sensor IDs and local stored results are retained. No connection to
parkrun is needed during setup or restart. Old records with only numeric venue IDs
use `Event <id>` when no venue name exists in the stored data; they are not silently
merged into one unknown venue.

Removed: API access and credentials, scraping, event-directory downloads, refresh
scheduling/actions, Get All Runs/Get New Runs buttons, next-location selection,
cancellation checks, and the saved web-page HTML importer. The removed controls
are cleaned from the entity registry. Remove dashboard cards and automations that
referenced them. Existing internal run history remains for statistics.

For a manual-file installation, replace the integration directory instead of
copying over it, so obsolete Python files are also removed. Never delete the
integration's `.storage` results files. If using HACS, download the 3.x version
and restart before testing the existing import automation.

## Troubleshooting and privacy

- **Count increases but no event:** confirm the watched folder/filter, listen for
  `imap_content`, and try a narrow date range or dedicated incoming folder. The
  count changing does not imply IMAP emitted every matching message.
- **Event but no import:** check automation traces, the IMAP `entry_id`, subject
  condition, configured athlete ID, and that the new code is loaded after restart.
- **No barcode found:** supply the full email with links, not a short preview or
  copied visible text. Fetch an HTML part if necessary.
- **Message not moved:** first check for an import error; then check the exact
  target-folder name and mailbox permissions. Failed imports deliberately remain.
- **Rolling record unknown:** provide dated results within the window. A reported
  PB or summary count alone is insufficient.

This integration has no outbound network client. Home Assistant's separate IMAP
integration connects to your mail provider; HACS connects to GitHub for updates.
Parsed records are saved locally. Raw email bodies and profile links are not saved
by Parkrun5k, but Home Assistant automation traces/service logging can contain the
submitted payload. Never include real mailbox credentials, profile links, barcode
IDs or private result exports in public issues or test fixtures.

This repository starts with clean history; no commits from the older integration
were copied. See [PUBLICATION.md](PUBLICATION.md) for release maintenance. The MIT license covers this project's code; it does not imply
endorsement or grant rights to third-party branding or email content.

## References

- [Home Assistant IMAP configuration and actions](https://www.home-assistant.io/integrations/imap/)
- [Apple iCloud Mail settings](https://support.apple.com/en-gb/102525)
- [HACS custom repositories](https://www.hacs.xyz/docs/faq/custom_repositories/)
- [HACS integration packaging](https://www.hacs.xyz/docs/publish/integration/)
- [HACS does not support private repositories](https://www.hacs.xyz/docs/faq/private_repositories/)
