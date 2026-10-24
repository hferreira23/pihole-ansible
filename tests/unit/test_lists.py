import copy
import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from ansible.module_utils import basic

from ansible_collections.hferreira23.pihole.plugins.module_utils import lists


ADDRESS = 'https://example.com/hosts.txt'
CURRENT = dict(address=ADDRESS, comment='original', groups=[1], enabled=True)


class ModuleExit(BaseException):
    def __init__(self, failed, payload):
        self.failed = failed
        self.payload = payload


@pytest.fixture(params=['block_list', 'allow_list'])
def harness(request, monkeypatch):
    """Run the real argument parser, replacing only I/O and module termination."""
    module = importlib.import_module('ansible_collections.hferreira23.pihole.plugins.modules.' + request.param)
    client = MagicMock()
    records = [copy.deepcopy(CURRENT)]
    client.group_management.get_groups.return_value = {'groups': [dict(id=1, name='Test')]}
    client.list_management.get_lists.side_effect = lambda **kwargs: {'lists': copy.deepcopy(records)}

    def update(address, **kwargs):
        next(item for item in records if item['address'] == address).update(
            {key: value for key, value in kwargs.items() if key != 'list_type'})
        return {'processed': {'success': [address], 'errors': []}}

    client.list_management.update_list.side_effect = update
    client.list_management.add_list.return_value = {'processed': {'errors': []}}
    client.list_management.delete_list.return_value = {}
    client.actions.run_gravity.return_value = 'arbitrary gravity output'
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(lists, 'PiHole6Client', factory)
    monkeypatch.setattr(lists, 'HAS_PIHOLE6API', True)

    def exit_json(self, **payload):
        raise ModuleExit(False, payload)

    def fail_json(self, **payload):
        raise ModuleExit(True, payload)

    monkeypatch.setattr(basic.AnsibleModule, 'exit_json', exit_json)
    monkeypatch.setattr(basic.AnsibleModule, 'fail_json', fail_json)

    def run(items=None, check=False, **params):
        args = dict(url='https://hole', password='secret', _ansible_check_mode=check)
        if items is not None:
            args['lists'] = items
        args.update(params)
        monkeypatch.setattr(basic, '_load_params', lambda: args)
        with pytest.raises(ModuleExit) as result:
            module.run_module()
        return result.value

    return SimpleNamespace(run=run, client=client, records=records, factory=factory,
                           list_type='block' if request.param == 'block_list' else 'allow')


def entry(**kwargs):
    return dict(address=ADDRESS, state='present', **kwargs)


def test_empty_memberships_update_once_then_converge(harness):
    first = harness.run([entry(groups=[])], update_gravity=True)
    assert not first.failed and first.payload['changed']
    assert harness.records[0]['groups'] == []
    assert harness.client.list_management.update_list.call_args.kwargs['groups'] == []
    second = harness.run([entry(groups=[])], update_gravity=True)
    assert not second.failed and not second.payload['changed']
    harness.client.list_management.update_list.assert_called_once()
    harness.client.actions.run_gravity.assert_called_once()


@pytest.mark.parametrize('legacy', [False, True])
def test_omitted_memberships_preserved_during_field_update(harness, legacy):
    params = dict(comment='new')
    result = (harness.run(address=ADDRESS, state='present', **params) if legacy
              else harness.run([entry(**params)]))
    assert not result.failed and result.payload['changed']
    assert harness.records[0]['groups'] == [1]
    assert not harness.run([entry(comment='new')]).payload['changed']


def test_legacy_empty_memberships(harness):
    result = harness.run(address=ADDRESS, state='present', groups=[])
    assert not result.failed and result.payload['changed']
    assert harness.records[0]['groups'] == []


@pytest.mark.parametrize('desired,existing,changed,action', [
    (entry(), [], True, 'added'),
    (dict(address=ADDRESS, state='absent'), [CURRENT], True, 'deleted'),
    (dict(address=ADDRESS, state='absent'), [], False, 'absent_already'),
    (entry(comment='new'), [CURRENT], True, 'updated'),
    (entry(enabled=False), [CURRENT], True, 'updated'),
    (entry(groups=[]), [CURRENT], True, 'updated'),
    (entry(groups=['tEsT']), [CURRENT], False, 'unchanged'),
    (entry(groups=[1]), [CURRENT], False, 'unchanged'),
    (entry(), [CURRENT], False, 'unchanged'),
])
def test_check_mode_compares_without_writes(harness, desired, existing, changed, action):
    harness.records[:] = copy.deepcopy(existing)
    result = harness.run([desired], check=True, update_gravity=True)
    assert not result.failed
    assert result.payload['changed'] is changed
    assert result.payload['result'][0]['action'] == action
    harness.client.list_management.get_lists.assert_called_once_with(list_type=harness.list_type)
    harness.client.list_management.add_list.assert_not_called()
    harness.client.list_management.update_list.assert_not_called()
    harness.client.list_management.delete_list.assert_not_called()
    harness.client.actions.run_gravity.assert_not_called()


@pytest.mark.parametrize('response', [
    {'error': {'key': 'bad_request', 'message': 'rejected', 'hint': 'details'}},
    {'processed': {'success': [], 'errors': [{'item': ADDRESS, 'error': 'invalid'}]}},
])
@pytest.mark.parametrize('action', ['create', 'update', 'delete'])
def test_write_errors_fail_and_retain_details(harness, action, response):
    desired = entry(comment='new')
    if action == 'create':
        harness.records.clear()
        method = harness.client.list_management.add_list
    elif action == 'update':
        method = harness.client.list_management.update_list
    else:
        desired = dict(address=ADDRESS, state='absent')
        method = harness.client.list_management.delete_list
    method.side_effect = None
    method.return_value = response
    result = harness.run([desired], update_gravity=True)
    assert result.failed and not result.payload['changed']
    assert result.payload['response'] == response
    harness.client.actions.run_gravity.assert_not_called()
    harness.client.close_session.assert_called_once()


@pytest.mark.parametrize('response', [{'error': 'denied'}, {}, {'groups': None}, {'groups': [{}]}])
def test_group_read_errors_fail_closed(harness, response):
    harness.client.group_management.get_groups.return_value = response
    result = harness.run([entry()])
    assert result.failed and not result.payload['changed']
    assert result.payload['response'] == response
    harness.client.list_management.get_lists.assert_not_called()
    harness.client.list_management.update_list.assert_not_called()


def test_group_read_exception_fails_closed(harness):
    harness.client.group_management.get_groups.side_effect = RuntimeError('unavailable')
    result = harness.run([entry()], check=True)
    assert result.failed and 'unavailable' in result.payload['msg']
    harness.client.list_management.add_list.assert_not_called()


def test_unknown_name_in_batch_prevents_partial_assignments(harness):
    result = harness.run([entry(comment='new'), dict(address='other', state='present', groups=['missing'])])
    assert result.failed and 'missing' in result.payload['msg']
    harness.client.list_management.update_list.assert_not_called()
    harness.client.list_management.add_list.assert_not_called()


@pytest.mark.parametrize('response', [{'error': 'denied'}, {}, {'lists': None}])
def test_list_read_errors_not_treated_as_absence(harness, response):
    harness.client.list_management.get_lists.side_effect = None
    harness.client.list_management.get_lists.return_value = response
    result = harness.run([entry()])
    assert result.failed and result.payload['response'] == response
    harness.client.list_management.add_list.assert_not_called()


def test_gravity_once_for_mixed_batch(harness):
    result = harness.run([entry(comment='new'), dict(address='other', state='present')], update_gravity=True)
    assert not result.failed and result.payload['changed']
    harness.client.actions.run_gravity.assert_called_once()
    assert harness.client.connection.connection_timeout == 60


def test_delete_success_runs_gravity_once(harness):
    result = harness.run([dict(address=ADDRESS, state='absent')], update_gravity=True)
    assert not result.failed and result.payload['changed']
    harness.client.list_management.delete_list.assert_called_once_with(ADDRESS, list_type=harness.list_type)
    harness.client.actions.run_gravity.assert_called_once()


def test_names_and_integer_ids_resolve_without_coercion(harness):
    harness.records.clear()
    result = harness.run([entry(groups=['tEsT', 0])])
    assert not result.failed and result.payload['changed']
    assert harness.client.list_management.add_list.call_args.kwargs['groups'] == [1, 0]


def test_empty_batch_does_not_fall_back_to_legacy(harness):
    result = harness.run([], address=ADDRESS, state='absent', update_gravity=True)
    assert not result.failed and not result.payload['changed']
    harness.client.list_management.delete_list.assert_not_called()
    harness.client.actions.run_gravity.assert_not_called()


def test_partial_batch_error_retains_prior_changes(harness):
    response = {'processed': {'errors': ['rejected']}}
    harness.client.list_management.add_list.return_value = response
    result = harness.run([entry(comment='new'), dict(address='other', state='present')], update_gravity=True)
    assert result.failed and result.payload['changed']
    assert result.payload['result'][0]['action'] == 'updated'
    assert result.payload['response'] == response
    harness.client.actions.run_gravity.assert_not_called()


def test_gravity_error_fails_and_keeps_mutation_changed(harness):
    harness.client.actions.run_gravity.return_value = {'error': 'gravity failed'}
    result = harness.run([entry(groups=[])], update_gravity=True)
    assert result.failed and result.payload['changed']
    assert result.payload['response'] == {'error': 'gravity failed'}


def test_tls_options_reach_client(harness):
    result = harness.run([entry()], validate_certs=False, ca_path='/private-ca.pem')
    assert not result.failed
    harness.factory.assert_called_once_with('https://hole', 'secret', validate_certs=False,
                                            ca_path='/private-ca.pem')
