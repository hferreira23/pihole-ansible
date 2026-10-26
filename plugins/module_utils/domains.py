"""Fail-closed planning and reconciliation of individual Pi-hole domains."""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_native
from ansible_collections.hferreira23.pihole.plugins.module_utils.api import (
    APIResponseError, failure_details, get_existing_groups, map_groups_to_ids,
    response_items, validate_response,
)
from ansible_collections.hferreira23.pihole.plugins.module_utils.client import (
    HAS_PIHOLE6API, PiHole6Client,
)


def domain_argument_spec():
    return dict(
        domains=dict(type='list', elements='dict', required=True, options=dict(
            domain=dict(type='str', required=True),
            type=dict(type='str', required=True, choices=['allow', 'deny']),
            kind=dict(type='str', default='exact', choices=['exact', 'regex']),
            state=dict(type='str', default='present', choices=['present', 'absent']),
            comment=dict(type='str'),
            groups=dict(type='list', elements='raw'),
            enabled=dict(type='bool'),
        )),
        url=dict(type='str', required=True),
        password=dict(type='str', required=True, no_log=True),
        validate_certs=dict(type='bool', default=True),
        ca_path=dict(type='path'),
    )


def domain_identity(item):
    """Canonicalize exact domains; regex identity remains case-sensitive."""
    domain = item['domain']
    if not domain or not domain.strip():
        raise ValueError('domain must not be empty')
    if item['kind'] == 'exact':
        domain = domain.encode('idna').decode('ascii').lower()
    return domain, item['type'], item['kind']


def index_domains(response):
    """Reject incomplete state rather than fabricate defaults for a PUT."""
    indexed = {}
    for item in response_items(response, 'domains'):
        if (not isinstance(item, dict) or not isinstance(item.get('domain'), str)
                or item.get('type') not in ('allow', 'deny')
                or item.get('kind') not in ('exact', 'regex')
                or type(item.get('enabled')) is not bool
                or not isinstance(item.get('groups'), list)
                or any(type(group) is not int for group in item['groups'])
                or (item.get('comment') is not None and not isinstance(item['comment'], str))):
            raise APIResponseError('Invalid domains response', response)
        try:
            identity = domain_identity(item)
        except (ValueError, UnicodeError) as error:
            raise APIResponseError('Invalid domains response: {0}'.format(error), response) from error
        if identity in indexed:
            raise APIResponseError('Duplicate domain identity in response', response)
        indexed[identity] = item
    return indexed


def plan_domain(item, existing, existing_groups):
    domain, domain_type, kind = domain_identity(item)
    planned = dict(domain=domain, type=domain_type, kind=kind)
    if item['state'] == 'absent':
        return dict(planned, action='deleted' if existing is not None else 'absent_already')
    groups = map_groups_to_ids(item.get('groups'), existing_groups)
    defaults = existing if existing is not None else dict(comment=None, groups=[], enabled=True)
    values = {key: defaults.get(key) if item.get(key) is None else item[key]
              for key in ('comment', 'enabled')}
    # Pi-hole stores empty comments as NULL. Compare and return the canonical
    # value so an explicit clear converges instead of issuing a PUT every run.
    values['comment'] = values['comment'] or None
    values['groups'] = defaults['groups'] if groups is None else sorted(set(groups))
    if existing is None:
        action = 'added'
    elif (values['comment'] != (existing.get('comment') or None) or values['enabled'] != existing['enabled']
          or set(values['groups']) != set(existing['groups'])):
        action = 'updated'
    else:
        action = 'unchanged'
    return dict(planned, action=action, values=values)


def validate_domain_inputs(items):
    identities = [domain_identity(item) for item in items]
    if len(set(identities)) != len(identities):
        raise ValueError('Duplicate domain/type/kind entries are not allowed in one invocation')


def reconcile_domains(module, client, result):
    items = module.params['domains']
    if not items:
        return
    existing_groups = get_existing_groups(client)
    current = index_domains(client.domain_management.get_domains())
    # Resolve and plan every entry before the first write. A batch is not atomic.
    plan = [plan_domain(item, current.get(domain_identity(item)), existing_groups) for item in items]
    methods = dict(added=client.domain_management.add_domain,
                   updated=client.domain_management.update_domain,
                   deleted=client.domain_management.delete_domain)
    for planned in plan:
        action = planned['action']
        entry = {key: value for key, value in planned.items() if key != 'values'}
        if 'values' in planned:
            entry.update(planned['values'])
        if action in methods:
            if not module.check_mode:
                response = methods[action](planned['domain'], domain_type=planned['type'],
                                           kind=planned['kind'], **planned.get('values', {}))
                validate_response(response, '{0} domain {1}'.format(action, planned['domain']))
                entry['response'] = response
            result['changed'] = True
        result['domains'].append(entry)


def run_module():
    module = AnsibleModule(argument_spec=domain_argument_spec(), supports_check_mode=True)
    result = dict(changed=False, domains=[])
    try:
        validate_domain_inputs(module.params['domains'])
    except (ValueError, UnicodeError) as error:
        module.fail_json(msg=to_native(error), **result)
    if not HAS_PIHOLE6API:
        module.fail_json(msg='The pihole6api module is required', **result)
    client = None
    try:
        client = PiHole6Client(module.params['url'], module.params['password'],
                              validate_certs=module.params['validate_certs'],
                              ca_path=module.params['ca_path'])
        reconcile_domains(module, client, result)
    except Exception as error:
        module.fail_json(msg='Error managing domains: {0}'.format(to_native(error)),
                         **failure_details(error), **result)
    finally:
        if client is not None:
            client.close_session()
    module.exit_json(**result)
