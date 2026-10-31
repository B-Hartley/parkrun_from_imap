"""Parse result emails without retaining message bodies or personal profile links."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from html import unescape
from html.parser import HTMLParser
import re
import json
from pathlib import Path
from datetime import datetime

from .records import improve_records, result_key, refresh_locations



def load_locales():
    """Load locale pattern files in lexical order."""
    folder = Path(__file__).with_name("languages")
    locales = []
    for path in sorted(folder.glob("*.json")):
        locale = json.loads(path.read_text(encoding="utf-8"))
        if locale["code"] != path.stem:
            raise ValueError("Locale filename and code differ")
        for key in ("result_subject", "volunteer_subject", "barcode"):
            re.compile(locale[key])
        for section in ("result", "volunteer"):
            for regex in locale[section].values():
                re.compile(regex)
        locales.append(locale)
    return locales


def choose_locale(subject):
    matches = []
    for locale in load_locales():
        for kind in ("result", "volunteer"):
            if re.search(locale[kind + "_subject"], subject, re.I):
                matches.append((locale, kind))
    if len(matches) != 1:
        raise ValueError("Unsupported or ambiguous email language")
    return matches[0]


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _seconds(value):
    pieces = [int(p) for p in value.split(":")]
    if len(pieces) != 3 or not 0 <= pieces[1] < 60 or not 0 <= pieces[2] < 60:
        raise ValueError("Invalid result time")
    seconds = pieces[0] * 3600 + pieces[1] * 60 + pieces[2]
    if seconds <= 0:
        raise ValueError("Invalid result time")
    return seconds


def parse_email(subject, body, athlete_id):
    """Validate an English result email against an explicitly selected runner."""
    athlete_id = str(athlete_id).upper().removeprefix("A")
    if not re.fullmatch(r"[0-9]+", athlete_id):
        raise ValueError("Invalid athlete ID")
    locale, kind = choose_locale(subject)
    decoded = re.sub(r"(?m)^\s*(?:>\s*)+", "", unescape(body))
    ids = set(re.findall(locale["barcode"], decoded, re.I))
    if ids and ids != {athlete_id}:
        raise ValueError("Email barcode does not match the selected runner")
    # Some plain-text messages omit links and the barcode. Require a barcode
    # in the full body rather than guessing from a first name.
    if not ids:
        raise ValueError("No barcode found; supply the complete email including links")
    if kind == "volunteer":
        return parse_volunteer_email(subject, decoded, locale)
    match = re.search(locale["result_subject"], subject, re.I)
    if not match:
        raise ValueError("Unrecognised parkrun result subject")
    venue, event_number, day = match.groups()
    day = datetime.strptime(day, locale["date_format"]).date().isoformat()
    parser = _Text()
    parser.feed(decoded)
    text = " ".join(" ".join(parser.parts).split())

    def required(pattern):
        result = re.search(pattern, text, re.I)
        if result is None:
            raise ValueError("Result email is incomplete or has an unsupported format")
        return result

    result_time = required(locale["result"]["time"]).group(1)
    _seconds(result_time)
    total = int(required(locale["result"]["total"]).group(1).replace(",", ""))
    if total < 1:
        raise ValueError("Invalid total runs")
    position = required(locale["result"]["position"])
    pos, field = (int(v.replace(",", "")) for v in position.groups())
    if not 1 <= pos <= field:
        raise ValueError("Invalid finishing position")
    run = {"date": day + "T00:00:00", "eventName": venue.strip(),
           "runNumber": int(event_number), "time": result_time, "position": pos,
           "totalAthletes": field, "reportedTotalRuns": total, "source": "email"}
    patterns = {key: locale["result"][key] for key in ("genderPosition", "ageCategoryPosition", "venueRuns") if key in locale["result"]}
    for key, pattern in patterns.items():
        if found := re.search(pattern, text, re.I):
            run[key] = int(found.group(1).replace(",", ""))
    if found := re.search(locale["result"]["ageCategory"], text, re.I):
        run["ageCategory"] = found.group(1).upper()
    if found := re.search(locale["result"]["ageGrade"], text, re.I):
        run["ageGrade"] = float(found.group(1))
    for key, pattern in ((key, locale["result"][key]) for key in ("venuePB", "yearBest") if key in locale["result"]):
        if found := re.search(pattern, text, re.I):
            _seconds(found.group(1))
            run[key] = found.group(1)
    return run


def merge_email(existing, run, runner_name, get_event_name):
    """Merge a result, preserving saved history and marking incomplete aggregates."""
    if run.get("activity") == "volunteer":
        return merge_volunteer_email(existing, run, runner_name, get_event_name)
    data = deepcopy(existing or {})
    runs = data.get("runs", [])

    def venue(item):
        name = item.get("eventName") or get_event_name(item.get("eventId"))
        return re.sub(r"\s+parkrun$", "", name, flags=re.I).strip().casefold()

    def same(a, b):
        same_venue = (a.get("eventId") is not None and a.get("eventId") == b.get("eventId")) or venue(a) == venue(b)
        return same_venue and a["date"][:10] == b["date"][:10] and str(a.get("runNumber")) == str(b.get("runNumber"))

    matched = next((r for r in runs if same(r, run)), {})
    updated = {**matched, **run}
    # A corrected email can omit an optional field. Do not carry old email
    # values into the correction; retain non-email legacy metadata only.
    if matched.get("source") == "email":
        updated = dict(run)
    runs = [r for r in runs if not same(r, run)] + [updated]
    runs.sort(key=lambda r: r["date"], reverse=True)
    # Run date, not delivery date or the maximum ever received, determines
    # the authoritative reported total. A corrected latest email may lower it.
    latest_report = next(r for r in runs if r.get("reportedTotalRuns") is not None)
    later_runs = sum(r["date"][:10] > latest_report["date"][:10] for r in runs)
    total = latest_report["reportedTotalRuns"] + later_runs
    complete = len(runs) == total
    data.update(name=runner_name, runs=runs, total_runs=total,
                latest_category=runs[0].get("ageCategory", "Unknown"),
                latest_milestone=next(m for m in (1000, 500, 250, 100, 50, 25, 0) if total >= m),
                result_source="email", history_complete=complete)
    data.setdefault("volunteer_count", None)
    data.setdefault("volunteer_roles", [])
    data.setdefault("volunteers", [])
    # Keep seeded unique-location totals until complete history can calculate
    # them. Partial history cannot tell whether a venue is a first-ever visit.
    if complete:
        data["unique_locations"] = len({venue(r) for r in runs})
    else:
        data.setdefault("unique_locations", None)
    for key in ("personal_best", "pb_date", "pb_location", "pb_event_id",
                "best_age_grade", "bag_date", "bag_location", "bag_event_id"):
        data.setdefault(key, None)
    key = result_key(run, get_event_name)
    # A newly received official result supersedes a correction to that run.
    data["manual_results"] = [r for r in data.get("manual_results", [])
                              if result_key(r, get_event_name) != key]
    data["excluded_results"] = [r for r in data.get("excluded_results", []) if tuple(r) != key]
    improve_records(data, [updated], get_event_name)
    return refresh_locations(data, get_event_name)


def parse_volunteer_email(subject, decoded, locale):
    """Parse an already identity-validated volunteer acknowledgement."""
    match = re.search(locale["volunteer_subject"], subject, re.I)
    if not match:
        raise ValueError("Unrecognised volunteering email subject")
    venue, day = match.groups()
    day = datetime.strptime(day, locale["date_format"]).date().isoformat()
    parser = _Text()
    parser.feed(decoded)
    text = " ".join(" ".join(parser.parts).split())
    confirmation = re.search(locale["volunteer"]["confirmation"], text, re.I)
    counts = re.search(locale["volunteer"]["counts"], text, re.I)
    if not confirmation or confirmation.group(1).strip().casefold() != venue.strip().casefold() or confirmation.group(2) != day or not counts:
        raise ValueError("Volunteering email is incomplete or does not match its subject")
    venue_count, total = (int(v.replace(',', '')) for v in counts.groups())
    if not 1 <= venue_count <= total:
        raise ValueError("Invalid volunteering totals")
    return {"activity": "volunteer", "date": day + "T00:00:00", "eventName": venue.strip(),
            "venueVolunteerCount": venue_count, "reportedVolunteerCredits": total, "source": "email"}


def merge_volunteer_email(existing, activity, runner_name, get_event_name):
    """Keep volunteer acknowledgements separate from run results and role totals."""
    data = deepcopy(existing or {})
    items = {result_key(v, get_event_name): v for v in data.get('volunteer_emails', [])}
    items[result_key(activity, get_event_name)] = dict(activity)
    history = sorted(items.values(), key=lambda v: v['date'], reverse=True)
    latest = history[0]
    total = latest['reportedVolunteerCredits']
    # Preserve undated legacy/manual totals until dated reports catch up.
    if 'volunteer_count_floor' not in data:
        data['volunteer_count_floor'] = data.get('volunteer_count') or 0
    total = max(total, data['volunteer_count_floor'])
    volunteers = [v for v in data.get('volunteers', []) if v.get('source') != 'email_volunteer']
    volunteers.extend(dict(v, source='email_volunteer') for v in history)
    data['volunteers'] = volunteers
    data.update(name=runner_name, volunteer_emails=history, volunteer_count=total,
                volunteer_report_date=max(latest['date'][:10], data.get('volunteer_report_date', '')),
                result_source='email')
    data['volunteer_history_complete'] = len({v['date'][:10] for v in history}) == total
    return refresh_locations(data, get_event_name)
