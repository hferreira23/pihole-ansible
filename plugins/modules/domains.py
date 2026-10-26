#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Hugo Ferreira (@hferreira23)
# MIT License

DOCUMENTATION = r'''
---
module: domains
short_description: Manage individual Pi-hole allow and deny domains
description:
  - Manages individual whitelist and blacklist entries in the Pi-hole v6 Domains tab, not feed subscriptions.
  - Supports exact domains and Pi-hole regular expressions, comments, enabled state, and group assignments.
  - Reads all domain types and kinds and plans the entire batch before writing.
extends_documentation_fragment:
  - hferreira23.pihole.connection
options:
  url:
    description: Base URL of the Pi-hole server, without the C(/api) suffix.
    type: str
    required: true
  password:
    description: Pi-hole API password. Use Ansible Vault or another secret store.
    type: str
    required: true
  domains:
    description:
      - Entries to reconcile. Unlisted entries are untouched; an empty list manages nothing.
      - Each identity is the combination of O(domains[].domain), O(domains[].type), and O(domains[].kind).
      - Duplicate identities fail before authentication. Change type or kind by explicitly removing the old identity and adding the new one.
    type: list
    elements: dict
    required: true
    suboptions:
      domain:
        description:
          - Exact domain name or Pi-hole regular expression. Must not be empty.
          - Exact names are lowercased and IDNA-encoded; regex strings remain unchanged and case-sensitive as identities.
          - Regex syntax is validated by Pi-hole during writes, not locally in check mode. Use YAML single quotes to preserve backslashes.
        type: str
        required: true
      type:
        description: V(allow) is the whitelist; V(deny) is the blacklist.
        type: str
        choices: [allow, deny]
        required: true
      kind:
        description: Match an exact domain or a Pi-hole regular expression.
        type: str
        choices: [exact, regex]
        default: exact
      state:
        description: Whether the identified entry should exist. Other fields are ignored for V(absent).
        type: str
        choices: [present, absent]
        default: present
      comment:
        description:
          - Omitted or null preserves an existing comment. C('') clears it. New entries default to null.
          - Pi-hole normalizes empty comments to null; cleared comments are returned as null and converge on subsequent runs.
        type: str
      groups:
        description:
          - Group names (case-insensitive) or integer IDs. Numeric strings are names, not IDs.
          - Omitted or null preserves existing memberships; C([]) clears them. New entries default to no memberships.
          - Unknown names fail before any writes. Referenced names must already exist, including in check mode.
        type: list
        elements: raw
      enabled:
        description:
          - Omitted or null preserves existing state. New entries default to enabled.
        type: bool
attributes:
  check_mode:
    support: full
    description: Authenticates and reads state, predicts actions, and skips domain writes.
  diff_mode:
    support: none
notes:
  - No gravity run is needed or performed for individual domain changes.
  - Failed or malformed reads never imply absence. HTTP errors, API C(error), and nonempty C(processed.errors) fail the task.
  - Batches are not transactions. Earlier successful writes and results remain on later failure; no rollback occurs.
  - Check mode does not validate server-side regex syntax or predict concurrent server changes.
seealso:
  - module: hferreira23.pihole.groups
  - module: hferreira23.pihole.allow_list
  - module: hferreira23.pihole.block_list
author:
  - Hugo Ferreira (@hferreira23)
'''

EXAMPLES = r'''
- name: Reconcile individual whitelist and blacklist entries
  hferreira23.pihole.domains:
    url: "{{ pihole_url }}"
    password: "{{ pihole_password }}"
    domains:
      - domain: allowed.example.com
        type: allow
        groups: [Default]
        comment: Required service
      - domain: '(^|\.)ads\.example\.com$'
        type: deny
        kind: regex
        groups: [0]
      - domain: obsolete.example.com
        type: deny
        state: absent

- name: Preview disabling a domain without changing its comment or memberships
  hferreira23.pihole.domains:
    url: "{{ pihole_url }}"
    password: "{{ pihole_password }}"
    domains:
      - domain: allowed.example.com
        type: allow
        enabled: false
  check_mode: true
'''

RETURN = r'''
changed:
  description: Whether any write succeeded, or would be required in check mode.
  type: bool
  returned: always
domains:
  description: Completed actions in input order, or predictions in check mode. Retained on later failure.
  type: list
  elements: dict
  returned: always
  contains:
    domain:
      description: Canonical exact domain or unchanged regex string.
      type: str
      returned: always
    type:
      description: Allow or deny list type.
      type: str
      returned: always
    kind:
      description: Exact or regex match kind.
      type: str
      returned: always
    action:
      description: One of C(added), C(updated), C(deleted), C(unchanged), or C(absent_already).
      type: str
      returned: always
    comment:
      description: Effective comment. Empty or cleared comments are normalized to null, matching Pi-hole.
      type: raw
      returned: for present entries
    groups:
      description: Effective integer group IDs.
      type: list
      elements: int
      returned: for present entries
    enabled:
      description: Effective enabled state.
      type: bool
      returned: for present entries
    response:
      description: Successful API write response. Not returned in check mode or for unchanged entries.
      type: dict
      returned: after successful writes
response:
  description: Original structured response when an API or response validation error supplies one.
  type: raw
  returned: on failure when available
status_code:
  description: HTTP status when available, including 200 for an API-level rejection.
  type: int
  returned: on failure when available
'''

from ansible_collections.hferreira23.pihole.plugins.module_utils.domains import run_module


def main():
    run_module()


if __name__ == '__main__':
    main()
