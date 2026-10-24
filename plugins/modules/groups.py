#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2023, Simon Barbett <simon@barbett.me>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: groups
short_description: Manage PiHole groups
description:
  - Create, update, or delete PiHole groups.
  - Fails if the group read fails, rather than treating a failed read as an empty server.
extends_documentation_fragment:
  - hferreira23.pihole.connection
attributes:
  check_mode:
    support: full
    description: Authenticates and reads existing groups to predict changes without group writes.
  diff_mode:
    support: none
notes:
  - HTTP errors, an API C(error) response, and nonempty C(processed.errors) fail the module.
  - Batches are not transactions; successful earlier changes are not rolled back after a later failure.
  - Check mode does not create groups for subsequent list or client tasks. Referenced groups must exist when those tasks read them.
seealso:
  - module: hferreira23.pihole.block_list
  - module: hferreira23.pihole.allow_list
  - module: hferreira23.pihole.clients
version_added: "1.0.0"
author:
  - Simon Barbett (@sbarbett)
options:
  groups:
    description:
      - List of groups to manage.
    type: list
    elements: dict
    required: true
    suboptions:
      name:
        description:
          - Name of the group.
        type: str
        required: true
      comment:
        description:
          - Comment for the group.
          - When updating, omission or C(null) preserves the existing comment.
          - Use C('') to clear the comment.
        type: str
        required: false
      enabled:
        description:
          - Whether the group is enabled.
          - Defaults to true if not specified.
        type: bool
        required: false
        default: true
      state:
        description:
          - Whether the group should exist or not.
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
# Supply connection variables from inventory and Ansible Vault.
- name: Create groups before assigning their names to lists or clients
  hferreira23.pihole.groups:
    groups:
      - name: Cameras
        comment: Camera devices
        state: present
      - name: IoT
        enabled: false
        state: present
      - name: Retired custom group
        state: absent
    url: "{{ pihole_url }}"
    password: "{{ pihole_password }}"
    ca_path: /etc/ssl/certs/private-ca.pem

- name: Preview changes to groups that already exist
  hferreira23.pihole.groups:
    url: "{{ pihole_url }}"
    password: "{{ pihole_password }}"
    groups:
      - name: Cameras
        state: present
        enabled: false
  check_mode: true
  register: group_preview

- name: Update enabled state while preserving the existing comment
  hferreira23.pihole.groups:
    url: "{{ pihole_url }}"
    password: "{{ pihole_password }}"
    groups:
      - name: Cameras
        state: present
        enabled: true
        # Omit comment to preserve it; comment: "" clears it.
'''

RETURN = r'''
groups:
  description: Per-group outcomes. In check mode, created, updated, and deleted are predictions.
  returned: always
  type: list
  elements: dict
  contains:
    name:
      description: Name of the group.
      returned: always
      type: str
      sample: PiHole Default
    comment:
      description: Comment for the group.
      returned: for present groups
      type: str
      sample: The default group
    enabled:
      description: Whether the group is enabled.
      returned: for present groups
      type: bool
      sample: true
    state:
      description: One of C(created), C(updated), C(deleted), or C(unchanged).
      returned: always
      type: str
      sample: created
changed:
  description: Whether a group changed, or would change in check mode. May be true after a partial batch failure.
  returned: always
  type: bool
response:
  description: Failed API response or malformed group read response, retaining server error details.
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
    failure_details, get_existing_groups, validate_response,
)


def create_group(client, name, comment=None, enabled=True):
    """
    Create a new group in PiHole.
    
    Args:
        client: PiHole6Client instance
        name: Name of the group
        comment: Comment for the group
        enabled: Whether the group is enabled
        
    Returns:
        dict: Response from the API
    """
    return client.group_management.add_group(name, comment=comment, enabled=enabled)


def update_group(client, name, comment=None, enabled=True):
    """
    Update an existing group in PiHole.
    
    Args:
        client: PiHole6Client instance
        name: Name of the group
        comment: Comment for the group
        enabled: Whether the group is enabled
        
    Returns:
        dict: Response from the API
    """
    return client.group_management.update_group(name, comment=comment, enabled=enabled)


def delete_group(client, name):
    """
    Delete a group from PiHole.
    
    Args:
        client: PiHole6Client instance
        name: Name of the group
        
    Returns:
        dict: Response from the API
    """
    return client.group_management.delete_group(name)


def batch_delete_groups(client, names):
    """
    Delete multiple groups from PiHole.
    
    Args:
        client: PiHole6Client instance
        names: List of group names to delete
        
    Returns:
        dict: Response from the API
    """
    return client.group_management.batch_delete_groups(names)


def main():
    module_args = dict(
        groups=dict(
            type='list',
            elements='dict',
            required=True,
            options=dict(
                name=dict(type='str', required=True),
                comment=dict(type='str', required=False, default=None),
                enabled=dict(type='bool', required=False, default=True),
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
        groups=[],
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    if not HAS_PIHOLE6API:
        module.fail_json(msg='The pihole6api module is required')

    url = module.params['url']
    password = module.params['password']
    groups = module.params['groups']

    client = None
    try:
        client = PiHole6Client(url, password, validate_certs=module.params['validate_certs'],
                              ca_path=module.params['ca_path'])
        
        existing_groups = get_existing_groups(client)
        
        # Groups to delete (state: absent)
        groups_to_delete = [group['name'] for group in groups if group['state'] == 'absent' and group['name'] in existing_groups]
        
        # Process groups
        for group in groups:
            name = group['name']
            state = group['state']
            comment = group.get('comment')
            enabled = group.get('enabled', True)
            
            if state == 'present':
                if name not in existing_groups:
                    # Create new group
                    if not module.check_mode:
                        response = create_group(client, name, comment, enabled)
                        validate_response(response, f'create group {name}')
                    result['changed'] = True
                    result['groups'].append({
                        'name': name,
                        'comment': comment,
                        'enabled': enabled,
                        'state': 'created'
                    })
                else:
                    # Check if update is needed
                    existing = existing_groups[name]
                    effective_comment = existing.get('comment') if comment is None else comment
                    update_needed = False
                    
                    if comment is not None and existing.get('comment') != comment:
                        update_needed = True
                    
                    if existing['enabled'] != enabled:
                        update_needed = True
                    
                    if update_needed:
                        if not module.check_mode:
                            response = update_group(client, name, effective_comment, enabled)
                            validate_response(response, f'update group {name}')
                        result['changed'] = True
                        result['groups'].append({
                            'name': name,
                            'comment': effective_comment,
                            'enabled': enabled,
                            'state': 'updated'
                        })
                    else:
                        # No change needed
                        result['groups'].append({
                            'name': name,
                            'comment': existing.get('comment'),
                            'enabled': existing['enabled'],
                            'state': 'unchanged'
                        })
        
        # Delete groups
        if groups_to_delete:
            if not module.check_mode:
                if len(groups_to_delete) == 1:
                    response = delete_group(client, groups_to_delete[0])
                else:
                    response = batch_delete_groups(client, groups_to_delete)
                validate_response(response, f'delete groups {", ".join(groups_to_delete)}')
            result['changed'] = True
            for name in groups_to_delete:
                result['groups'].append({'name': name, 'state': 'deleted'})
        
        module.exit_json(**result)
    except Exception as e:
        module.fail_json(msg=f'Error managing groups: {to_native(e)}', **failure_details(e), **result)
    finally:
        if client is not None:
            client.close_session()


if __name__ == '__main__':
    main()
