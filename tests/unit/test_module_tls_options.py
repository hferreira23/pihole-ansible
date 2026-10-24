import importlib
from unittest.mock import MagicMock

import pytest
import requests
from ansible.module_utils import basic


class ModuleFailure(BaseException):
    def __init__(self, payload):
        self.payload = payload


@pytest.mark.parametrize('name,params', [
    ('block_list', dict(address='https://example.com/hosts', state='present')),
    ('allow_list', dict(address='https://example.com/allow', state='present')),
    ('groups', dict(groups=[dict(name='Test', state='present')])),
    ('clients', dict(clients=[dict(name='192.0.2.1', state='present')])),
    ('local_a_record', dict(host='example.com', ip='192.0.2.1', state='present')),
    ('local_aaaa_record', dict(host='example.com', ip='2001:db8::1', state='present')),
    ('local_cname', dict(host='alias.example.com', target='example.com', state='present')),
    ('listening_mode', dict(mode='local')),
    ('dhcp_config', dict(state='absent')),
    ('dhcp_remove_lease', dict(ip='192.0.2.1')),
])
@pytest.mark.parametrize('tls,expected', [
    ({}, dict(validate_certs=True, ca_path=None)),
    (dict(ca_path='/private-ca.pem'), dict(validate_certs=True, ca_path='/private-ca.pem')),
    (dict(validate_certs=False), dict(validate_certs=False, ca_path=None)),
])
def test_tls_options_and_safe_auth_failure(monkeypatch, name, params, tls, expected):
    module = importlib.import_module('ansible_collections.hferreira23.pihole.plugins.modules.' + name)
    target = module
    if name in ('allow_list', 'block_list'):
        target = importlib.import_module('ansible_collections.hferreira23.pihole.plugins.module_utils.lists')
    factory = MagicMock(side_effect=requests.exceptions.SSLError('untrusted certificate'))
    monkeypatch.setattr(target, 'PiHole6Client', factory)
    args = dict(url='https://hole', password='secret', **params, **tls)
    monkeypatch.setattr(basic, '_load_params', lambda: args)

    def fail_json(self, **payload):
        raise ModuleFailure(payload)

    monkeypatch.setattr(basic.AnsibleModule, 'fail_json', fail_json)
    with pytest.raises(ModuleFailure) as error:
        module.main()
    assert 'untrusted certificate' in error.value.payload['msg']
    assert error.value.payload['changed'] is False
    factory.assert_called_once_with('https://hole', 'secret', **expected)
