#!/usr/bin/python
# -*- coding: utf-8 -*-

from ansible_collections.hferreira23.pihole.plugins.module_utils.lists import run_module as manage_lists

DOCUMENTATION = r'''
---
module: block_list
short_description: Manage Pi-hole block lists via the v6 API
description:
  - Adds, updates, or removes block lists, individually or in batches.
  - Manages feed subscriptions, not individual blocked domains.
  - Supports explicit membership clearing, read-only check-mode predictions, and change-driven gravity updates.
extends_documentation_fragment:
  - hferreira23.pihole.connection
  - hferreira23.pihole.list_management
seealso:
  - module: hferreira23.pihole.allow_list
  - module: hferreira23.pihole.groups
author:
  - Shane Barbetta (@sbarbett)
  - Hugo Ferreira (@hferreira23)
'''

EXAMPLES = r'''
# Feed URLs below are placeholders; replace them with your own sources.
# Supply pihole_password from Ansible Vault or another secret store.
- name: Manage several block-list feeds and run gravity only after changes
  hferreira23.pihole.block_list:
    url: https://pihole.example.com
    password: "{{ pihole_password }}"
    lists:
      - address: https://example.com/hosts.txt
        state: present
        groups: [Default]
      - address: https://example.com/disabled-hosts.txt
        state: present
        enabled: false
        groups: [0]  # Integer IDs are accepted alongside group names
      - address: https://example.com/old.txt
        state: absent
    update_gravity: true
    gravity_timeout: 300  # Allow a longer gravity request for a large deployment

- name: Update a comment without changing existing memberships
  hferreira23.pihole.block_list:
    url: "{{ pihole_url }}"
    password: "{{ pihole_password }}"
    address: https://example.com/hosts.txt
    state: present
    comment: Managed by Ansible
    # groups is omitted deliberately; existing memberships are preserved

- name: Clear every membership using the legacy single-entry format
  hferreira23.pihole.block_list:
    url: https://pihole.example.com
    password: "{{ pihole_password }}"
    ca_path: /etc/ssl/certs/private-ca.pem
    address: https://example.com/hosts.txt
    state: present
    groups: []

- name: Preview a membership change without list writes or gravity
  hferreira23.pihole.block_list:
    url: "{{ pihole_url }}"
    password: "{{ pihole_password }}"
    lists:
      - address: https://example.com/hosts.txt
        state: present
        groups: []
    update_gravity: true  # Still skipped in check mode
  check_mode: true
  register: block_list_preview

- name: Display the predicted actions
  ansible.builtin.debug:
    var: block_list_preview.result

# For an explicitly trusted self-signed endpoint only, validate_certs: false
# opts out of verification. Prefer ca_path, as shown above.
'''

RETURN = r'''
result:
  description:
    - Per-list actions, including predicted actions in check mode, followed by a gravity entry if run.
    - On failure, includes entries completed before the failed operation.
  type: list
  elements: dict
  returned: always
  contains:
    address:
      description: Feed URL. Not present for the gravity entry.
      type: str
      returned: for each list entry
      sample: https://example.com/hosts.txt
    action:
      description:
        - One of C(added), C(updated), C(deleted), C(unchanged), C(absent_already), or C(run_gravity).
        - In check mode these describe predicted actions, not completed writes.
      type: str
      returned: always
      sample: updated
    response:
      description: Successful API response. Omitted for predicted writes in check mode.
      type: raw
      returned: after an actual mutation or gravity run
    current:
      description: Current API list data when the list is already in the desired state.
      type: dict
      returned: when action is unchanged
  sample:
    - address: https://example.com/hosts.txt
      action: updated
changed:
  description:
    - Whether a list changed or would change in check mode.
    - Can be true on failure if an earlier write succeeded; batches are not rolled back.
  type: bool
  returned: always
  sample: true
response:
  description: Failed API response or malformed read response, retaining server error details and processed.errors.
  type: raw
  returned: on failure when an API response is available
  sample:
    processed:
      errors:
        - item: https://example.com/hosts.txt
          error: Rejected by the server
status_code:
  description: HTTP status of a failed API response. May be 200 when the response body contains an API error.
  type: int
  returned: on failure when the transport supplies an HTTP status
  sample: 400
'''


def run_module():
    manage_lists('block')


def main():
    run_module()


if __name__ == '__main__':
    main()
