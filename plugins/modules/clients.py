#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2023, Simon Barbett <simon@barbett.me>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: clients
short_description: Manage PiHole clients
description:
  - Create, update, or delete PiHole clients.
  - Reads groups and clients before making assignments; failed reads are not treated as an empty server.
extends_documentation_fragment:
  - hferreira23.pihole.connection
attributes:
  check_mode:
    support: full
    description: Authenticates and reads existing groups and clients to predict changes without client writes.
  diff_mode:
    support: none
notes:
  - Unknown group names fail before any client writes in the batch; they are never silently discarded.
  - Referenced groups must already exist, including in check mode. A previous check-mode group task does not create them.
  - HTTP errors, an API C(error) response, and nonempty C(processed.errors) fail the module.
  - Batches are not transactions; successful earlier changes are not rolled back after a later failure.
seealso:
  - module: hferreira23.pihole.groups
version_added: "1.0.0"
author:
  - Simon Barbett (@sbarbett)
options:
  clients:
    description:
      - List of clients to manage.
    type: list
    elements: dict
    required: true
    suboptions:
      name:
        description:
          - The client IP address or CIDR range.
        type: str
        required: true
      comment:
        description:
          - Comment for the client.
          - When updating, omission or C(null) preserves the existing comment.
          - Use C('') to clear the comment.
        type: str
        required: false
      groups:
        description:
          - Complete desired membership set as case-insensitive group names or unquoted integer IDs.
          - Unknown names fail the module. Numeric strings are names, not integer IDs.
          - Both omission and C([]) clear existing client memberships. Unlike the list modules, omission does not preserve them.
        type: list
        elements: raw
        required: false
        default: []
      state:
        description:
          - Whether the client should exist or not.
        type: str
        required: true
        choices: [ present, absent ]
  url:
    description:
      - Base URL of the Pi-hole instance, without the C(/api) suffix.
    type: str
    required: true
  password:
    description:
      - Pi-hole API password or application password. Its value is hidden from module output.
    type: str
    required: true
'''

EXAMPLES = r'''
# Create custom groups with hferreira23.pihole.groups before using their names.
- name: Assign clients to existing groups using names and integer IDs
  hferreira23.pihole.clients:
    clients:
      - name: 192.168.30.0/24
        comment: Default VLAN
        groups:
          - Default
          - 1  # Replace with an existing group ID
        state: present
      - name: 192.168.40.0/24
        groups:
          - Default
        state: present
      - name: 192.168.50.0/24
        state: absent
    url: "{{ pihole_url }}"
    password: "{{ pihole_password }}"
    ca_path: /etc/ssl/certs/private-ca.pem

- name: Clear every membership for one client
  hferreira23.pihole.clients:
    url: "{{ pihole_url }}"
    password: "{{ pihole_password }}"
    clients:
      - name: 192.168.30.0/24
        state: present
        groups: []

- name: Preview an assignment without changing client memberships
  hferreira23.pihole.clients:
    url: "{{ pihole_url }}"
    password: "{{ pihole_password }}"
    clients:
      - name: 192.168.40.0/24
        state: present
        groups: [Default]
  check_mode: true
  register: client_preview

- name: Change group assignment while preserving the client's comment
  hferreira23.pihole.clients:
    url: "{{ pihole_url }}"
    password: "{{ pihole_password }}"
    clients:
      - name: 192.168.40.0/24
        state: present
        groups: [Default]
        # Omit comment to preserve it; comment: "" clears it.
'''

RETURN = r'''
clients:
  description: Per-client outcomes. In check mode, created, updated, and deleted are predictions.
  returned: always
  type: list
  elements: dict
  contains:
    name:
      description: The client IP address or CIDR range.
      returned: always
      type: str
      sample: 192.168.30.0/24
    comment:
      description: Comment for the client.
      returned: for present clients
      type: str
      sample: Default VLAN
    groups:
      description: Requested group names or integer IDs; unchanged clients report resolved group names.
      returned: for present clients
      type: list
      elements: raw
      sample: ["Default", "test"]
    state:
      description: One of C(created), C(updated), C(deleted), or C(unchanged).
      returned: always
      type: str
      sample: created
changed:
  description: Whether a client changed, or would change in check mode. May be true after a partial batch failure.
  returned: always
  type: bool
response:
  description: Failed API response or malformed read response, retaining server error details.
  returned: on failure when an API response is available
  type: raw
status_code:
  description: HTTP status of a failed API response, possibly 200 for API errors in a successful HTTP response.
  returned: on failure when the transport supplies an HTTP status
  type: int
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_native

from ansible_collections.hferreira23.pihole.plugins.module_utils.client import HAS_PIHOLE6API, PiHole6Client
from ansible_collections.hferreira23.pihole.plugins.module_utils.api import (
    failure_details, get_existing_groups, map_groups_to_ids, response_items, validate_response,
)


def get_existing_clients(client):
    """
    Get existing clients from PiHole.
    
    Args:
        client: PiHole6Client instance
        
    Returns:
        dict: Mapping of client addresses to client details
    """
    response = client.client_management.get_clients()
    clients = response_items(response, 'clients')
    return {client_data['client']: client_data for client_data in clients}


def create_client(client, name, comment=None, groups=None):
    """
    Create a new client in PiHole.
    
    Args:
        client: PiHole6Client instance
        name: Client IP address or CIDR range
        comment: Comment for the client
        groups: List of group IDs
        
    Returns:
        dict: Response from the API
    """
    return client.client_management.add_client(name, comment=comment, groups=groups or [])


def update_client(client, name, comment=None, groups=None):
    """
    Update an existing client in PiHole.
    
    Args:
        client: PiHole6Client instance
        name: Client IP address or CIDR range
        comment: Comment for the client
        groups: List of group IDs
        
    Returns:
        dict: Response from the API
    """
    return client.client_management.update_client(name, comment=comment, groups=groups or [])


def delete_client(client, name):
    """
    Delete a client from PiHole.
    
    Args:
        client: PiHole6Client instance
        name: Client IP address or CIDR range
        
    Returns:
        dict: Response from the API
    """
    return client.client_management.delete_client(name)


def batch_delete_clients(client, names):
    """
    Delete multiple clients from PiHole.
    
    Args:
        client: PiHole6Client instance
        names: List of client IP addresses or CIDR ranges
        
    Returns:
        dict: Response from the API
    """
    # The batch_delete_clients method expects dictionaries with an item key.
    return client.client_management.batch_delete_clients([{"item": name} for name in names])


def main():
    module_args = dict(
        clients=dict(
            type='list',
            elements='dict',
            required=True,
            options=dict(
                name=dict(type='str', required=True),
                comment=dict(type='str', required=False, default=None),
                groups=dict(type='list', elements='raw', required=False, default=[]),
                state=dict(type='str', required=True, choices=['present', 'absent']),
            ),
        ),
        url=dict(type='str', required=True),
        password=dict(type='str', required=True, no_log=True),
        validate_certs=dict(type='bool', default=True),
        ca_path=dict(type='path'),
    )

    result = dict(
        changed=False,
        clients=[],
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    if not HAS_PIHOLE6API:
        module.fail_json(msg='The pihole6api module is required')

    url = module.params['url']
    password = module.params['password']
    clients = module.params['clients']

    client = None
    try:
        client = PiHole6Client(url, password, validate_certs=module.params['validate_certs'],
                              ca_path=module.params['ca_path'])
        
        # Get existing groups and clients
        existing_groups = get_existing_groups(client)
        existing_clients = get_existing_clients(client)
        
        # Resolve the whole batch before making any assignments.
        resolved_groups = {item['name']: map_groups_to_ids(item.get('groups', []), existing_groups)
                           for item in clients if item['state'] == 'present'}
        
        # Clients to delete (state: absent)
        clients_to_delete = [client_data['name'] for client_data in clients 
                            if client_data['state'] == 'absent' and client_data['name'] in existing_clients]
        
        # Process clients
        for client_data in clients:
            name = client_data['name']
            state = client_data['state']
            comment = client_data.get('comment')
            group_names = client_data.get('groups', [])
            
            # Map group names to IDs
            group_ids = resolved_groups.get(name, [])
            
            if state == 'present':
                if name not in existing_clients:
                    # Create new client
                    if not module.check_mode:
                        response = create_client(client, name, comment, group_ids)
                        validate_response(response, f'create client {name}')
                    result['changed'] = True
                    result['clients'].append({
                        'name': name,
                        'comment': comment,
                        'groups': group_names,
                        'state': 'created'
                    })
                else:
                    # Check if update is needed
                    existing = existing_clients[name]
                    effective_comment = existing.get('comment') if comment is None else comment
                    update_needed = False
                    
                    if comment is not None and existing.get('comment') != comment:
                        update_needed = True
                    
                    # Compare group IDs
                    existing_group_ids = set(existing.get('groups', []))
                    desired_group_ids = set(group_ids)
                    if existing_group_ids != desired_group_ids:
                        update_needed = True
                    
                    if update_needed:
                        if not module.check_mode:
                            response = update_client(client, name, effective_comment, group_ids)
                            validate_response(response, f'update client {name}')
                        result['changed'] = True
                        result['clients'].append({
                            'name': name,
                            'comment': effective_comment,
                            'groups': group_names,
                            'state': 'updated'
                        })
                    else:
                        # No change needed
                        # Map existing group IDs back to names for the result
                        existing_group_names = []
                        for group_id in existing.get('groups', []):
                            for group_name, details in existing_groups.items():
                                if details['id'] == group_id:
                                    existing_group_names.append(group_name)
                                    break
                        
                        result['clients'].append({
                            'name': name,
                            'comment': existing.get('comment'),
                            'groups': existing_group_names,
                            'state': 'unchanged'
                        })
        
        # Delete clients
        if clients_to_delete:
            if not module.check_mode:
                if len(clients_to_delete) == 1:
                    response = delete_client(client, clients_to_delete[0])
                else:
                    response = batch_delete_clients(client, clients_to_delete)
                validate_response(response, f'delete clients {", ".join(clients_to_delete)}')
            result['changed'] = True
            for name in clients_to_delete:
                result['clients'].append({'name': name, 'state': 'deleted'})
        
        module.exit_json(**result)
    except Exception as e:
        module.fail_json(msg=f'Error managing clients: {to_native(e)}', **failure_details(e), **result)
    finally:
        if client is not None:
            client.close_session()


if __name__ == '__main__':
    main()
