"""Migration of existing stored records, entirely offline."""
from copy import deepcopy
from .records import improve_records, refresh_locations


def get_event_name(event_id):
    """Keep unidentified legacy venues distinct without downloading a directory."""
    return f"Event {event_id}" if event_id is not None else "Unknown event"


def prepare_saved_data(cached, runner_name):
    """Preserve records and materialize names already present in saved data."""
    data = deepcopy(cached or {})
    names = {}
    for field in ('runs', 'manual_results', 'volunteers', 'volunteer_emails'):
        for item in data.get(field, []):
            name = item.get('eventShortName') or item.get('eventName')
            if name and item.get('eventId') is not None:
                names[str(item['eventId'])] = name
    for prefix in ('pb', 'bag'):
        if data.get(f'{prefix}_event_id') is not None and data.get(f'{prefix}_location'):
            names[str(data[f'{prefix}_event_id'])] = data[f'{prefix}_location']
    for field in ('runs', 'manual_results', 'volunteers', 'volunteer_emails'):
        for item in data.get(field, []):
            item['eventName'] = item.get('eventShortName') or item.get('eventName') or names.get(str(item.get('eventId'))) or get_event_name(item.get('eventId'))
    data['name'] = runner_name
    data.setdefault('total_runs', None)
    data.setdefault('volunteer_count', None)
    data.setdefault('history_complete', False)
    data.setdefault('volunteer_history_complete', False)
    data.setdefault('result_source', 'manual')
    if data.get('runs') and not data.get('records_version'):
        improve_records(data, data['runs'], get_event_name)
    return refresh_locations(data, get_event_name)
