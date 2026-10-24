"""Shared response validation and fail-closed group resolution."""


class APIResponseError(ValueError):
    def __init__(self, message, response):
        super().__init__(message)
        self.response = response


def validate_response(response, operation):
    """Pi-hole can report rejected writes inside an HTTP-success response."""
    if isinstance(response, dict):
        processed = response.get('processed') or {}
        if 'error' in response or (isinstance(processed, dict) and processed.get('errors')):
            raise APIResponseError('Failed to {0}: {1}'.format(operation, response), response)
    return response


def response_items(response, key):
    validate_response(response, 'read {0}'.format(key))
    if not isinstance(response, dict) or not isinstance(response.get(key), list):
        raise APIResponseError('Invalid {0} response'.format(key), response)
    return response[key]


def get_existing_groups(client):
    response = client.group_management.get_groups()
    groups = response_items(response, 'groups')
    if any(not isinstance(group, dict) or not isinstance(group.get('name'), str)
           or type(group.get('id')) is not int for group in groups):
        raise APIResponseError('Invalid groups response', response)
    return {group['name']: group for group in groups}


def map_groups_to_ids(group_items, existing_groups):
    """Accept integer IDs or case-insensitive names; never drop unknown names."""
    if group_items is None:
        return None
    names = {name.casefold(): details['id'] for name, details in existing_groups.items()}
    group_ids = []
    for item in group_items:
        if type(item) is int:
            group_ids.append(item)
        elif isinstance(item, str) and item.casefold() in names:
            group_ids.append(names[item.casefold()])
        else:
            raise ValueError('Unknown group name or invalid ID: {0!r}'.format(item))
    return group_ids


def failure_details(error):
    """Keep structured API errors available in Ansible failure output."""
    details = {}
    for name in ('response', 'status_code'):
        if hasattr(error, name):
            details[name] = getattr(error, name)
    return details
