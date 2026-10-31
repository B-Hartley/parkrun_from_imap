# Adding a new email language

The built-in English definition is [en.json](custom_components/parkrun5k/languages/en.json).
Copy it to `custom_components/parkrun5k/languages/<language-code>.json` (for
example `de.json`), change `code`, `name`, the patterns, `date_format` and
`decimal_separator`. Publish the new file in this repository and reinstall/update
the integration; restart Home Assistant before testing.

The integration chooses the language from a matching email **subject**, not the
runner's configured country. Two different locales must not match the same subject.
Each pattern is a case-insensitive Python regular expression; parentheses around
extracted values are **capturing groups**. In JSON, backslashes need doubling:
`\\d` in regex becomes `\\\\d` in the JSON source.

Required capture groups:

| Pattern | Groups |
| --- | --- |
| `result_subject` | event name; event number; date |
| `volunteer_subject` | event name; date |
| `barcode` | numeric athlete barcode |
| `result.time` | HH:MM:SS |
| `result.total` | lifetime run count |
| `result.position` | finishing position; event participant count |
| `volunteer.confirmation` | event name; date (same text as subject) |
| `volunteer.counts` | volunteering occasions at event; total credits |

Optional `result` entries: `genderPosition`, `ageCategoryPosition`,
`venueRuns`, `ageCategory`, `ageGrade`, `venuePB`, `yearBest`.
The optional patterns each capture one value.

Dates use Python strptime format: `%Y-%m-%d` for 2026-10-31,
`%d/%m/%Y` for 31/10/2026. For decimal age grades choose
`decimal_separator` `.` or `,`.

**Safety:** Do not remove the barcode pattern. Every email must carry the
matching barcode; incorrect barcodes and unsupported subjects are rejected.
Use complete, redacted real email samples when developing a new definition.
Only the English definition is currently tested against English examples;
other languages require real samples before they can be described as supported.

**IMAP automation:** The README's default IMAP subject filters and automation
conditions are English-specific. For a new language, change both filters to use
the translated subject prefixes. The parser itself selects language automatically
when an email is submitted to `parkrun5k.import_email`. Separate incoming
folders/automations per athlete are still recommended.
