"""Best-known records and validated manual summary edits."""
from copy import deepcopy
from datetime import date
import math
import re


def time_seconds(value):
    """Accept MM:SS or HH:MM:SS, rejecting malformed and zero times."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,3}:\d{2}(?::\d{2})?", value):
        raise ValueError("Time must be MM:SS or HH:MM:SS")
    parts = [int(p) for p in value.split(':')]
    if parts[-1] >= 60 or (len(parts) == 3 and parts[-2] >= 60):
        raise ValueError("Invalid minutes or seconds")
    seconds = parts[0] * 60 + parts[1] if len(parts) == 2 else parts[0] * 3600 + parts[1] * 60 + parts[2]
    if seconds <= 0:
        raise ValueError("Time must be greater than zero")
    return seconds


def improve_records(data, runs, get_event_name):
    """Preserve records and improve them with available evidence only."""
    best = time_seconds(data['personal_best']) if data.get('personal_best') not in (None, 'Unknown', '00:00') else None
    grade = data.get('best_age_grade')
    year_bests = data.setdefault('year_bests', {})
    for run in runs:
        year = run['date'][:4]
        for value in (run.get('time'), run.get('yearBest')):
            if value and (not year_bests.get(year) or time_seconds(value) < time_seconds(year_bests[year])):
                seconds = time_seconds(value)
                year_bests[year] = f'{seconds // 60:02d}:{seconds % 60:02d}'
        location = run.get('eventName') or get_event_name(run.get('eventId'))
        candidates = [(run.get('time'), run.get('date'), location, run.get('eventId'), 'run'),
                      (run.get('venuePB'), None, location, run.get('eventId'), 'email_venue_pb'),
                      (run.get('yearBest'), None, None, None, 'email_year_best')]
        for value, day, place, event_id, source in candidates:
            if not value:
                continue
            seconds = time_seconds(value)
            if best is None or seconds < best or (seconds == best and not data.get('pb_date') and day):
                best = seconds
                data.update(personal_best=f'{seconds // 60:02d}:{seconds % 60:02d}',
                            pb_date=day, pb_location=place, pb_event_id=event_id, pb_source=source)
        value = run.get('ageGrade')
        if value is not None and (grade is None or float(value) > float(grade) or (float(value) == float(grade) and not data.get('bag_date'))):
            grade = float(value)
            data.update(best_age_grade=grade, bag_date=run.get('date'),
                        bag_location=location, bag_event_id=run.get('eventId'), bag_source='run')
    data['records_version'] = 1
    return data


MANUAL_FIELDS = {
    'year_best', 'year_best_year', 'total_runs', 'unique_locations', 'volunteer_count', 'latest_category',
    'personal_best', 'pb_date', 'pb_location', 'pb_event_id',
    'best_age_grade', 'bag_date', 'bag_location', 'bag_event_id',
}


def manual_update(existing, updates, runner_name):
    """Apply explicit corrections atomically; omitted values remain unchanged."""
    if not updates or set(updates) - MANUAL_FIELDS:
        raise ValueError('Supply at least one supported summary field')
    changes = dict(updates)
    if ('year_best' in changes) != ('year_best_year' in changes):
        raise ValueError('Supply year_best and year_best_year together')
    for key, value in changes.items():
        if key in {'total_runs', 'unique_locations', 'volunteer_count', 'pb_event_id', 'bag_event_id'}:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or int(value) != value:
                raise ValueError(f'{key} must be a non-negative integer')
            changes[key] = int(value)
        elif key == 'best_age_grade':
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 200:
                raise ValueError('best_age_grade must be between 0 and 200 percent')
        elif key == 'year_best_year':
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 2004 <= value <= 9999 or int(value) != value:
                raise ValueError('year_best_year must be a year from 2004 onwards')
            changes[key] = int(value)
        elif key in ('personal_best', 'year_best'):
            seconds = time_seconds(value)
            changes[key] = f'{seconds // 60:02d}:{seconds % 60:02d}'
        elif key in {'pb_date', 'bag_date'}:
            if not isinstance(value, str):
                raise ValueError(f'{key} must be YYYY-MM-DD')
            changes[key] = date.fromisoformat(value).isoformat() + 'T00:00:00'
        elif not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise ValueError(f'{key} must be a non-empty string of at most 200 characters')
    data = deepcopy(existing or {})
    # A manual record correction can be slower/lower. Do not retain provenance
    # from a different old record when only its value is being replaced.
    for value_key, prefix in (('personal_best', 'pb'), ('best_age_grade', 'bag')):
        if value_key in changes:
            for suffix in ('date', 'location', 'event_id'):
                data[f'{prefix}_{suffix}'] = None
            data[f'{prefix}_source'] = 'manual'
    if 'year_best' in changes:
        data.setdefault('year_bests', {})[str(changes.pop('year_best_year'))] = changes.pop('year_best')
    data.update(changes)
    if 'volunteer_count' in changes:
        data['volunteer_count_floor'] = changes['volunteer_count']
        data['volunteer_history_complete'] = False
    data['name'] = runner_name
    data['result_source'] = data.get('result_source', 'manual')
    if data['result_source'] not in ('email', 'manual'):
        data['result_source'] = 'manual'
    total = data.get('total_runs')
    if total is not None:
        data['latest_milestone'] = next(m for m in (1000, 500, 250, 100, 50, 25, 0) if total >= m)
        data['history_complete'] = len(data.get('runs', [])) == total
    data['records_version'] = 1
    return data


def result_key(run, get_event_name):
    location = run.get('eventName') or get_event_name(run.get('eventId'))
    return run['date'][:10], re.sub(r'\s+parkrun$', '', location, flags=re.I).replace('&', 'and').strip().casefold()


def dated_results(data, get_event_name):
    """Combine email history with explicit corrections, one result per day/venue."""
    results = {result_key(r, get_event_name): dict(r) for r in data.get('runs', [])}
    for r in data.get('manual_results', []):
        key = result_key(r, get_event_name)
        results[key] = {**results.get(key, {}), **r}
    excluded = {tuple(key) for key in data.get('excluded_results', [])}
    return [r for key, r in results.items() if key not in excluded]


def rolling_records(data, today, get_event_name):
    """Records in (same calendar date last year, today], inclusive of today."""
    try:
        start = today.replace(year=today.year - 1)
    except ValueError:  # Feb 29 follows Feb 28 in the preceding non-leap year.
        start = today.replace(year=today.year - 1, day=28)
    eligible = []
    for run in dated_results(data, get_event_name):
        day = date.fromisoformat(run['date'][:10])
        if start < day <= today:
            eligible.append(run)
    # Most recent achievement wins a tie, with venue as a stable secondary key.
    eligible.sort(key=lambda r: (r['date'], r.get('eventName', '')), reverse=True)
    timed = [r for r in eligible if r.get('time')]
    graded = [r for r in eligible if r.get('ageGrade') is not None]
    time_run = min(timed, key=lambda r: time_seconds(r['time'])) if timed else None
    grade_run = max(graded, key=lambda r: float(r['ageGrade'])) if graded else None

    def record(run, kind):
        if run is None:
            return {'value': None, 'date': None, 'location': None}
        seconds = time_seconds(run['time']) if kind == 'time' else None
        value = f'{seconds // 60:02d}:{seconds % 60:02d}' if kind == 'time' else round(float(run['ageGrade']), 2)
        return {'value': value, 'date': run['date'][:10],
                'location': run.get('eventName') or get_event_name(run.get('eventId')),
                'event_id': run.get('eventId'), 'source': run.get('source', 'legacy')}
    return {'time': record(time_run, 'time'), 'age_grade': record(grade_run, 'age_grade'),
            'window_start_exclusive': start.isoformat(), 'window_end': today.isoformat(),
            'known_results_in_window': len(eligible)}


def structured_update(existing, updates, runner_name, today, get_event_name):
    """Validated summary/record corrections and dated evidence for rolling sensors."""
    if not isinstance(updates, dict) or not updates or set(updates) - {'summary', 'personal_best', 'best_age_grade', 'results', 'remove_results', 'locations'}:
        raise ValueError('updates must contain supported summary, record or result sections')
    data = deepcopy(existing or {})
    if 'locations' in updates:
        locations = updates['locations']
        if not isinstance(locations, dict) or set(locations) - {'run', 'volunteer'}:
            raise ValueError('locations supports run and volunteer lists')
        for kind, names in locations.items():
            if not isinstance(names, list) or len(names) > 1000 or any(not isinstance(n, str) or not n.strip() or len(n) > 200 for n in names):
                raise ValueError('Locations must be lists of non-empty venue names')
            data[f'{kind}_location_seeds'] = [n.strip() for n in names]
    summary = updates.get('summary', {})
    if not isinstance(summary, dict) or set(summary) - {'total_runs', 'unique_locations', 'volunteer_count', 'latest_category', 'year_best', 'year_best_year'}:
        raise ValueError('Unsupported summary fields')
    explicit = dict(summary)
    for section, value_field, prefix in (('personal_best', 'time', 'pb'), ('best_age_grade', 'value', 'bag')):
        if section not in updates:
            continue
        record = updates[section]
        if not isinstance(record, dict) or value_field not in record or set(record) - {value_field, 'date', 'location', 'event_id'}:
            raise ValueError(f'Invalid {section} object')
        explicit[section] = record[value_field]
        for key in ('date', 'location', 'event_id'):
            if key in record:
                explicit[f'{prefix}_{key}'] = record[key]
        if 'date' in record and date.fromisoformat(record['date']) > today:
            raise ValueError('Record date cannot be in the future')
    manual = {result_key(r, get_event_name): r for r in data.get('manual_results', [])}
    excluded = {tuple(key) for key in data.get('excluded_results', [])}
    evidence = []
    for section in ('remove_results', 'results'):
        items = updates.get(section, [])
        if not isinstance(items, list) or len(items) > 1000:
            raise ValueError(f'{section} must be a list of at most 1000 results')
        for item in items:
            allowed = {'date', 'location'} if section == 'remove_results' else {'date', 'location', 'time', 'age_grade'}
            if not isinstance(item, dict) or not {'date', 'location'} <= set(item) or set(item) - allowed:
                raise ValueError(f'Invalid {section} item')
            day = date.fromisoformat(item['date'])
            if day > today:
                raise ValueError('Result date cannot be in the future')
            location = item['location']
            if not isinstance(location, str) or not location.strip() or len(location) > 200:
                raise ValueError('Result location must be a non-empty string of at most 200 characters')
            run = {'date': day.isoformat() + 'T00:00:00', 'eventName': location.strip(), 'source': 'manual'}
            key = result_key(run, get_event_name)
            if section == 'remove_results':
                manual.pop(key, None)
                excluded.add(key)
                continue
            if not {'time', 'age_grade'} & set(item):
                raise ValueError('Each result requires time or age_grade')
            if 'time' in item:
                seconds = time_seconds(item['time'])
                run['time'] = f'{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}'
            if 'age_grade' in item:
                manual_update({}, {'best_age_grade': item['age_grade']}, runner_name)
                run['ageGrade'] = float(item['age_grade'])
            manual[key] = {**manual.get(key, {}), **run}
            excluded.discard(key)
            evidence.append(run)
    data['manual_results'] = list(manual.values())
    data['excluded_results'] = [list(key) for key in sorted(excluded)]
    improve_records(data, evidence, get_event_name)
    # Explicit records take precedence, including downward corrections.
    if explicit:
        data = manual_update(data, explicit, runner_name)
    else:
        data.update(name=runner_name, result_source=data.get('result_source', 'manual'), records_version=1)
        if data['result_source'] not in ('email', 'manual'):
            data['result_source'] = 'manual'
    refresh_locations(data, get_event_name)
    return data


def refresh_locations(data, get_event_name):
    """Expose the known venue list without claiming partial history is complete."""
    venues = {}
    for run in dated_results(data, get_event_name):
        key = result_key(run, get_event_name)[1]
        location = run.get('eventName') or get_event_name(run.get('eventId'))
        day = run['date'][:10]
        item = venues.setdefault(key, {'location': location, 'runs': 0, 'first_run': day, 'last_run': day})
        item['runs'] += 1
        item['first_run'] = min(item['first_run'], day)
        item['last_run'] = max(item['last_run'], day)
    for location in data.get('run_location_seeds', []):
        key = result_key({'date': '', 'eventName': location}, get_event_name)[1]
        venues.setdefault(key, {'location': location, 'runs': 0, 'first_run': None, 'last_run': None})
    data['location_details'] = sorted(venues.values(), key=lambda v: v['location'].casefold())
    if data.get('history_complete'):
        data['unique_locations'] = len(venues)
    elif data.get('unique_locations') is not None:
        data['unique_locations'] = max(data['unique_locations'], len(venues))
    else:
        data['unique_locations'] = None
    volunteer_venues = {}
    volunteer_history = {}
    for item in data.get('volunteers', []) + data.get('volunteer_emails', []):
        item = dict(item)
        item['eventName'] = item.get('eventShortName') or item.get('eventName') or get_event_name(item.get('eventId'))
        if item.get('date') and item.get('eventName'):
            key = result_key(item, get_event_name)
            volunteer_history[key] = {**volunteer_history.get(key, {}), **item}
    for item in sorted(volunteer_history.values(), key=lambda v: v['date']):
        key = result_key(item, get_event_name)[1]
        day = item['date'][:10]
        entry = volunteer_venues.setdefault(key, {'location': item['eventName'], 'known_occasions': 0,
                                                 'first_known_date': day, 'last_known_date': day})
        entry['known_occasions'] += 1
        entry['last_known_date'] = day
        if 'venueVolunteerCount' in item:
            entry['reported_occasions'] = item['venueVolunteerCount']
            entry['reported_as_of'] = day
    for location in data.get('volunteer_location_seeds', []):
        key = result_key({'date': '', 'eventName': location}, get_event_name)[1]
        volunteer_venues.setdefault(key, {'location': location, 'known_occasions': 0,
                                          'first_known_date': None, 'last_known_date': None})
    data['volunteer_location_details'] = sorted(volunteer_venues.values(), key=lambda v: v['location'].casefold())
    combined = {}
    for kind, entries in (('run', venues), ('volunteer', volunteer_venues)):
        for key, entry in entries.items():
            combined.setdefault(key, {'location': entry['location'], 'run': False, 'volunteer': False})[kind] = True
    data['visited_location_details'] = sorted(combined.values(), key=lambda v: v['location'].casefold())
    return data
