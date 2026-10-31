# Parkrun from IMAP

Track parkrun runs, personal bests, age grades, locations and volunteering locally in Home Assistant.

**No parkrun API, scraping or login required.** Import your existing All Results HTML
once, then let Home Assistant's separate IMAP integration receive future parkrun result
and volunteering emails. This is an independent community integration, not affiliated
with parkrun.

## 1. Install using Marketplace

1. In Home Assistant, open **Marketplace**.
2. Click **Add from link** in the top right.
3. Paste `https://github.com/B-Hartley/parkrun_from_imap` and click **Add**.
4. Open **Parkrun from IMAP**, choose **Install/Download**, and **restart Home Assistant**.
5. Open **Settings → Devices & services → Add integration → Parkrun from IMAP**.
6. Enter your athlete barcode (with or without `A`) and display name.
   Add a separate integration entry for each runner you track.

**Using an older Home Assistant with HACS instead of Marketplace?**
Follow the [HACS installation instructions](INSTALL_HACS.md), then return to step 2 below.

Requires Home Assistant 2026.3 or newer. This is a custom repository, not a default
Marketplace listing.

## 2. Import your complete running history

This is a **one-time** import that populates historic times, PBs, age grades and
venues **before** you start importing new emails.

1. In your browser, open your parkrun profile and follow the link to **All Results**
   (the URL ends in `/parkrunner/YOUR_NUMBER/all/`). **Do not use the summary profile
   page**, which shows only the most recent results.
2. Use **View page source** (`Ctrl+U` on Windows), select all (`Ctrl+A`),
   then copy (`Ctrl+C`).
3. In Home Assistant go to **Developer Tools → Actions** and select
   **Parkrun5k: Import all-results HTML** (`parkrun5k.import_html`).
4. Enter the runner's barcode and paste the *complete page source* into **HTML**.
   Run the action, then check Total Runs, Personal Best, Best Age Grade and venues.
5. Repeat separately for other runners and their own barcodes.

The importer runs locally, checks that the barcode matches the selected runner and
that every row is present, and merges data without duplicating existing runs. It
does not fetch the webpage. It does not import detailed volunteering history; the
email step below gathers future volunteering credits and venues.

## 3. Configure Home Assistant IMAP

Home Assistant's **IMAP** integration reads the mailbox; Parkrun from IMAP itself
does not store your email credentials.

1. Go to **Settings → Devices & services → Add integration → IMAP**.
2. Configure your email account and the folder that receives your parkrun messages.
   A dedicated parkrun folder is easiest, although `INBOX` also works.
3. Configure the IMAP search expression below. **Do not use `UNSEEN`**; results
   should import even after you have read the message.
4. Create a folder called **Parkrun Processed** in the same mailbox. The automation
   in step 4 moves a message only after a successful import.
5. Leave the IMAP custom event template blank. The automation uses `imap.fetch`
   to retrieve the complete message instead of relying on truncated event text.

For iCloud Mail, use server `imap.mail.me.com`, port `993`, SSL/TLS and an
Apple app-specific password. Enter the full email address as the username if needed.

Use this IMAP search query for normal messages:

```text
FROM "noreply@parkrun.com" OR SUBJECT "Your result from" SUBJECT "Thank you for volunteering at"
```

If you are testing **forwarded** emails from your own address, temporarily replace
it with:

```text
OR SUBJECT "Your result from" SUBJECT "Thank you for volunteering at"
```

Keep the complete original email (including links and the athlete barcode). The
importer checks identity; it rejects messages without a matching barcode.

## 4. Link IMAP to the runner (copy-and-paste automation)

**A normal YAML automation is simpler than a blueprint here.** It needs only two
values: the IMAP integration's `entry_id` and the runner's barcode. It is easy
to inspect in Home Assistant and does not require downloading or updating a separate
blueprint.

1. Go to **Developer Tools → Events** and listen for `imap_content`.
2. Reload IMAP or send a matching email. Find `entry_id` in the emitted event.
   **Use the IMAP entry ID**, not a sensor entity ID or the Parkrun entry ID.
3. Create an automation and choose **Edit in YAML**. Copy the example below.
4. Replace `YOUR_IMAP_ENTRY_ID` and `1234567` with your values.
5. Check that the mailbox contains **Parkrun Processed**, then save and enable.
   For the first test, you may remove the final `imap.move` action.
6. Send a matching result email, check the automation trace and runner's sensors,
   then confirm the message moves to **Parkrun Processed**.

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

**Important:** Do not use `continue_on_error` on the import action: if parsing
fails, the email should remain in the incoming folder for investigation.
For multiple runners use **separate filtered mailbox folders / IMAP entries and
one automation per runner**. Do not direct two runner automations at the same
unfiltered inbox; the wrong-barcode automation will reject the message.
IMAP events are not a reliable bulk historical backfill—use step 2 for history.
Existing emails are not guaranteed to retrigger merely because you change a filter.

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

## Advanced manual imports and corrections

Three actions are available: **`parkrun5k.import_html`**, **`parkrun5k.import_email`**,
and **`parkrun5k.update_data`**. All validate inputs before saving. Changes survive
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

English result and volunteering acknowledgement formats are included as editable locale patterns. The full
body must contain the matching barcode in a profile link or other supported barcode
reference. The importer never follows links. Names alone cannot verify identity.
If the plain-text part omits links, use the complete HTML body (for example the
appropriate part fetched with IMAP's `imap.fetch_part`) instead. To backfill all historic runs, use the All Results HTML import described above.

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

## Email languages and community translations

The email importer reads language-specific regex definitions from
[`custom_components/parkrun5k/languages/`](custom_components/parkrun5k/languages/).
English (`en.json`) is provided first. Other languages can be added with a small
JSON file rather than changing Python code. The language is selected by matching
the email subject; the athlete barcode must still match before any data is saved.
See [LANGUAGES.md](LANGUAGES.md) for the pattern fields and contribution guide.

**For non-English mail**, adjust the IMAP search and automation's English subject
conditions in steps 3–4 to match the actual language. Only English is currently
verified; please contribute redacted real examples to support other languages.

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

See [PUBLICATION.md](PUBLICATION.md) for release maintenance. The MIT license covers this project's code; it does not imply
endorsement or grant rights to third-party branding or email content.

## References

- [Home Assistant IMAP configuration and actions](https://www.home-assistant.io/integrations/imap/)
- [Apple iCloud Mail settings](https://support.apple.com/en-gb/102525)
- [HACS custom repositories](https://www.hacs.xyz/docs/faq/custom_repositories/)
- [HACS integration packaging](https://www.hacs.xyz/docs/publish/integration/)
- [HACS Marketplace documentation](https://www.hacs.xyz/docs/marketplace/)
