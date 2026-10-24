import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from ansible.module_utils import basic


class ModuleExit(BaseException):
    def __init__(self, failed, payload):
        self.failed = failed
        self.payload = payload


@pytest.fixture(params=['groups', 'clients'])
def harness(request, monkeypatch):
    module = importlib.import_module('ansible_collections.hferreira23.pihole.plugins.modules.' + request.param)
    client = MagicMock()
    client.group_management.get_groups.return_value = {'groups': []}
    client.client_management.get_clients.return_value = {'clients': []}
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(module, 'PiHole6Client', factory)
    monkeypatch.setattr(module, 'HAS_PIHOLE6API', True)

    def terminate(failed):
        def finish(self, **payload):
            raise ModuleExit(failed, payload)
        return finish

    monkeypatch.setattr(basic.AnsibleModule, 'exit_json', terminate(False))
    monkeypatch.setattr(basic.AnsibleModule, 'fail_json', terminate(True))

    def run(items=None, check=False):
        args = dict(url='https://hole', password='secret', _ansible_check_mode=check)
        args[request.param] = items or [dict(name='new', state='present')]
        monkeypatch.setattr(basic, '_load_params', lambda: args)
        with pytest.raises(ModuleExit) as result:
            module.main()
        return result.value

    return SimpleNamespace(client=client, run=run, kind=request.param)


@pytest.mark.parametrize('response', [{'error': {'message': 'denied'}}, {}, {'groups': None}])
@pytest.mark.parametrize('check', [False, True])
def test_group_reads_fail_closed(harness, response, check):
    harness.client.group_management.get_groups.return_value = response
    result = harness.run(check=check)
    assert result.failed and not result.payload['changed']
    assert result.payload['response'] == response
    harness.client.group_management.add_group.assert_not_called()
    harness.client.client_management.add_client.assert_not_called()


def test_group_read_exceptions_fail_closed(harness):
    harness.client.group_management.get_groups.side_effect = RuntimeError('read failed')
    result = harness.run()
    assert result.failed and 'read failed' in result.payload['msg']
    assert not result.payload['changed']


def test_unknown_client_group_prevents_any_batch_writes(monkeypatch):
    from ansible_collections.hferreira23.pihole.plugins.modules import clients

    client = MagicMock()
    client.group_management.get_groups.return_value = {'groups': [dict(id=1, name='Test')]}
    client.client_management.get_clients.return_value = {'clients': []}
    monkeypatch.setattr(clients, 'PiHole6Client', lambda *args, **kwargs: client)
    args = dict(url='https://hole', password='secret', clients=[
        dict(name='first', state='present', groups=['Test']),
        dict(name='second', state='present', groups=['missing']),
    ])
    monkeypatch.setattr(basic, '_load_params', lambda: args)

    def fail_json(self, **payload):
        raise ModuleExit(True, payload)

    monkeypatch.setattr(basic.AnsibleModule, 'fail_json', fail_json)
    with pytest.raises(ModuleExit) as result:
        clients.main()
    assert result.value.failed and 'missing' in result.value.payload['msg']
    client.client_management.add_client.assert_not_called()


@pytest.mark.parametrize('action', ['create', 'update', 'delete', 'batch_delete'])
def test_processed_errors_fail_with_details(harness, action):
    kind = 'group' if harness.kind == 'groups' else 'client'
    api = getattr(harness.client, kind + '_management')
    response = {'processed': {'errors': [{'item': 'new', 'error': 'rejected'}]}}
    items = [dict(name='new', state='present', comment='new')]
    if action in ('update', 'delete', 'batch_delete'):
        harness.client.group_management.get_groups.return_value = {
            'groups': [dict(id=1, name='new', comment='old', enabled=True),
                       dict(id=2, name='other', comment='', enabled=True)]}
        harness.client.client_management.get_clients.return_value = {
            'clients': [dict(client='new', comment='old', groups=[]),
                        dict(client='other', comment='', groups=[])]}
    if action in ('delete', 'batch_delete'):
        items = [dict(name='new', state='absent')]
        if action == 'batch_delete':
            items.append(dict(name='other', state='absent'))
    method = {'create': 'add_' + kind, 'update': 'update_' + kind,
              'delete': 'delete_' + kind, 'batch_delete': 'batch_delete_' + harness.kind}[action]
    getattr(api, method).return_value = response
    result = harness.run(items)
    assert result.failed and not result.payload['changed']
    assert result.payload['response'] == response
