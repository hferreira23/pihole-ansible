"""Common reconciliation for allow_list and block_list."""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_native
from ansible_collections.hferreira23.pihole.plugins.module_utils.api import (
    APIResponseError, failure_details, get_existing_groups, map_groups_to_ids,
    response_items, validate_response,
)
from ansible_collections.hferreira23.pihole.plugins.module_utils.client import (
    HAS_PIHOLE6API, PiHole6Client,
)


def list_argument_spec():
    entry = dict(
        address=dict(type='str', required=True),
        state=dict(type='str', choices=['present', 'absent'], required=True),
        comment=dict(type='str', default=None),
        groups=dict(type='list', elements='raw', default=None),
        enabled=dict(type='bool', default=True),
    )
    return dict(
        lists=dict(type='list', elements='dict', options=entry),
        address=dict(type='str'),
        state=dict(type='str', choices=['present', 'absent']),
        comment=dict(type='str', default=None),
        groups=dict(type='list', elements='raw', default=None),
        enabled=dict(type='bool', default=True),
        password=dict(type='str', required=True, no_log=True),
        url=dict(type='str', required=True),
        validate_certs=dict(type='bool', default=True),
        ca_path=dict(type='path'),
        update_gravity=dict(type='bool', default=False),
        gravity_timeout=dict(type='int', default=60),
    )


def plan_list(item, existing, existing_groups):
    """Resolve the desired write without changing server state."""
    address = item['address']
    if item['state'] == 'absent':
        return dict(address=address, action='deleted' if existing else 'absent_already')

    groups = map_groups_to_ids(item.get('groups'), existing_groups)
    comment = item.get('comment')
    enabled = item.get('enabled', True)
    if existing is None:
        return dict(address=address, action='added', values=dict(
            comment=comment, groups=groups if groups is not None else [], enabled=enabled))

    needs_update = (
        (comment is not None and existing.get('comment') != comment)
        or (groups is not None and set(existing.get('groups', [])) != set(groups))
        or existing.get('enabled') != enabled
    )
    if not needs_update:
        return dict(address=address, action='unchanged', current={'lists': [existing]})
    # The external endpoint wrapper serializes omitted groups as []; carry the
    # current values explicitly so an unrelated update cannot clear memberships.
    return dict(address=address, action='updated', values=dict(
        comment=existing.get('comment') if comment is None else comment,
        groups=existing.get('groups', []) if groups is None else groups,
        enabled=enabled))


def reconcile_lists(module, client, list_type, result):
    items = module.params['lists']
    if items is None:
        items = [{key: module.params[key] for key in
                  ('address', 'state', 'comment', 'groups', 'enabled')}]
    existing_groups = get_existing_groups(client)
    response = client.list_management.get_lists(list_type=list_type)
    current = response_items(response, 'lists')
    if any(not isinstance(item, dict) or not isinstance(item.get('address'), str) for item in current):
        raise APIResponseError('Invalid lists response', response)
    by_address = {item['address']: item for item in current}
    # Validate the whole batch before the first mutation, including group names.
    plan = [plan_list(item, by_address.get(item['address']), existing_groups) for item in items]
    methods = {'added': client.list_management.add_list,
               'updated': client.list_management.update_list,
               'deleted': client.list_management.delete_list}
    for planned in plan:
        entry = {key: value for key, value in planned.items() if key != 'values'}
        action = planned['action']
        if action in methods:
            if not module.check_mode:
                response = methods[action](planned['address'], list_type=list_type,
                                           **planned.get('values', {}))
                validate_response(response, '{0} list {1}'.format(action, planned['address']))
                entry['response'] = response
            result['changed'] = True
        result['result'].append(entry)

    if module.params['update_gravity'] and result['changed'] and not module.check_mode:
        response = client.actions.run_gravity(timeout=module.params['gravity_timeout'])
        validate_response(response, 'run gravity')
        result['result'].append(dict(action='run_gravity', response=response))


def run_module(list_type):
    module = AnsibleModule(
        argument_spec=list_argument_spec(), supports_check_mode=True,
        required_one_of=[['lists', 'address']], required_by={'address': ['state']},
    )
    result = dict(changed=False, result=[])
    if module.params['gravity_timeout'] <= 0:
        module.fail_json(msg='gravity_timeout must be a positive number of seconds', **result)
    if not HAS_PIHOLE6API:
        module.fail_json(msg='The pihole6api module is required', **result)

    client = None
    try:
        client = PiHole6Client(module.params['url'], module.params['password'],
                              validate_certs=module.params['validate_certs'],
                              ca_path=module.params['ca_path'])
        reconcile_lists(module, client, list_type, result)
    except Exception as error:
        module.fail_json(msg='Error managing {0} lists: {1}'.format(list_type, to_native(error)),
                         **failure_details(error), **result)
    finally:
        if client is not None:
            client.close_session()
    module.exit_json(**result)
