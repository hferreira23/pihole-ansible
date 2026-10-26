#!/usr/bin/python
# -*- coding: utf-8 -*-

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.hferreira23.pihole.plugins.module_utils.client import PiHole6Client, HAS_PIHOLE6API

if not HAS_PIHOLE6API:
    raise ImportError("The 'pihole6api' Python module is required. Run 'pip install pihole6api' to install it.")

DOCUMENTATION = r'''
---
module: listening_mode
short_description: Manage Pi-hole listening mode via Pi-hole v6 API.
description:
    - This module updates the DNS listening mode on a Pi-hole v6 instance using the pihole6api Python client.
    - If the specified listening mode is already set, no changes will be made.
extends_documentation_fragment: [hferreira23.pihole.connection]
options:
    mode:
        description:
            - The desired listening mode for Pi-hole.
            - Choices are "local", "single", "bind", or "all".
        required: true
        type: str
        choices: ['local', 'single', 'bind', 'all']
    password:
        description:
            - The API password for the Pi-hole instance.
        required: true
        type: str
        no_log: true
    url:
        description:
            - The URL of the Pi-hole instance.
        required: true
        type: str
author:
    - Shane Barbetta (@sbarbett)
    - Hugo Ferreira (@hferreira23)
'''

EXAMPLES = r'''
- name: Set Pi-hole listening mode to "all"
  hferreira23.pihole.listening_mode:
    url: "https://your-pihole.example.com"
    password: "{{ pihole_password }}"
    mode: "all"

- name: Ensure Pi-hole is using "local" listening mode
  hferreira23.pihole.listening_mode:
    url: "https://your-pihole.example.com"
    password: "{{ pihole_password }}"
    mode: "local"
'''

RETURN = r'''
result:
    description: The API response from the Pi-hole server.
    type: dict
    returned: always
changed:
    description: Whether the listening mode was changed.
    type: bool
    returned: always
'''

def run_module():
    module_args = dict(
        mode=dict(type='str', choices=['local', 'single', 'bind', 'all'], required=True),
        password=dict(type='str', required=True, no_log=True),
        url=dict(type='str', required=True),
        validate_certs=dict(type='bool', default=True),
        ca_path=dict(type='path'),
    )

    result = dict(
        changed=False,
        result={}
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    mode = module.params['mode'].upper()  # Convert to uppercase to match API response format
    password = module.params['password']
    url = module.params['url']

    if module.check_mode:
        module.exit_json(**result)

    client = None
    try:
        client = PiHole6Client(url, password, validate_certs=module.params['validate_certs'],
                              ca_path=module.params['ca_path'])

        # Get current listening mode
        current_config = client.config.get_config_section("dns/listeningMode")
        current_mode = current_config.get("config", {}).get("dns", {}).get("listeningMode", "").upper()

        if current_mode == mode:
            # Already set, no changes needed
            result['changed'] = False
            result['result'] = {"msg": f"Listening mode already set to '{mode}'"}
        else:
            # Change listening mode
            new_config = {"dns": {"listeningMode": mode}}
            response = client.config.update_config(new_config)
            result['changed'] = True
            result['result'] = response

        module.exit_json(**result)

    except Exception as e:
        module.fail_json(msg=f"Error updating listening mode: {e}", **result)
    finally:
        if client is not None:
            client.close_session()

def main():
    run_module()

if __name__ == '__main__':
    main()
