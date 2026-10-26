"""Individual domain reconciliation through real Ansible argument parsing."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from ansible.module_utils import basic
from ansible_collections.hferreira23.pihole.plugins.module_utils import domains
from ansible_collections.hferreira23.pihole.plugins.module_utils.client import PiHoleAPIError


class ModuleExit(BaseException):
    def __init__(self, failed, payload):
        self.failed = failed
        self.payload = payload


@pytest.fixture
def harness(monkeypatch):
    client = MagicMock()
    api = client.domain_management
    api.get_domains.return_value = {'domains': []}
    for method in ('add_domain', 'update_domain', 'delete_domain'):
        getattr(api, method).return_value = {}
    client.group_management.get_groups.return_value = {
        'groups': [dict(name='Default', id=0), dict(name='IoT', id=2)]}
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(domains, 'PiHole6Client', factory)
    monkeypatch.setattr(domains, 'HAS_PIHOLE6API', True)

    def terminate(failed):
        def finish(self, **payload):
            raise ModuleExit(failed, payload)
        return finish

    monkeypatch.setattr(basic.AnsibleModule, 'exit_json', terminate(False))
    monkeypatch.setattr(basic.AnsibleModule, 'fail_json', terminate(True))

    def run(items=None, check=False, **extra):
        args = dict(url='https://hole', password='secret', _ansible_check_mode=check,
                    domains=[dict(domain='example.com', type='deny')] if items is None else items)
        args.update(extra)
        monkeypatch.setattr(basic, '_load_params', lambda: args)
        with pytest.raises(ModuleExit) as result:
            domains.run_module()
        return result.value

    return SimpleNamespace(client=client, api=api, factory=factory, run=run)


def record(**overrides):
    return dict(dict(domain='example.com', type='deny', kind='exact', comment='keep',
                     groups=[2], enabled=False), **overrides)


def assert_no_writes(harness):
    for method in ('add_domain', 'update_domain', 'delete_domain', 'batch_delete_domains'):
        getattr(harness.api, method).assert_not_called()
    harness.client.actions.run_gravity.assert_not_called()


@pytest.mark.parametrize('domain_type', ['allow', 'deny'])
@pytest.mark.parametrize('kind', ['exact', 'regex'])
@pytest.mark.parametrize('check', [False, True])
def test_create_all_types_and_kinds(harness, domain_type, kind, check):
    item = dict(domain='example.com', type=domain_type, kind=kind, comment='new', groups=['iOt', 0, 2])
    result = harness.run([item], check=check)
    assert not result.failed and result.payload['changed']
    row, = result.payload['domains']
    assert row['action'] == 'added' and row['groups'] == [0, 2]
    assert row['enabled'] is True and row['comment'] == 'new'
    if check:
        assert_no_writes(harness)
        assert 'response' not in row
    else:
        harness.api.add_domain.assert_called_once_with(
            'example.com', domain_type=domain_type, kind=kind, comment='new', groups=[0, 2], enabled=True)
    harness.client.close_session.assert_called_once()


def test_create_defaults_and_empty_batch(harness):
    result = harness.run()
    assert not result.failed
    row, = result.payload['domains']
    assert row['comment'] is None and row['groups'] == [] and row['enabled'] is True
    harness.api.reset_mock()
    assert not harness.run([]).payload['changed']
    harness.api.get_domains.assert_not_called()
    assert_no_writes(harness)


@pytest.mark.parametrize('check', [False, True])
@pytest.mark.parametrize('change,expected', [
    ({'comment': ''}, {'comment': None, 'groups': [2], 'enabled': False}),
    ({'comment': 'new'}, {'comment': 'new', 'groups': [2], 'enabled': False}),
    ({'enabled': True}, {'comment': 'keep', 'groups': [2], 'enabled': True}),
    ({'groups': []}, {'comment': 'keep', 'groups': [], 'enabled': False}),
    ({'groups': ['Default']}, {'comment': 'keep', 'groups': [0], 'enabled': False}),
])
def test_updates_preserve_other_fields(harness, check, change, expected):
    harness.api.get_domains.return_value = {'domains': [record()]}
    result = harness.run([dict(domain='example.com', type='deny', **change)], check=check)
    assert not result.failed and result.payload['changed']
    row, = result.payload['domains']
    assert row['action'] == 'updated'
    assert {key: row[key] for key in expected} == expected
    if check:
        assert_no_writes(harness)
    else:
        harness.api.update_domain.assert_called_once_with('example.com', domain_type='deny', kind='exact', **expected)


@pytest.mark.parametrize('extra', [{}, dict(comment=None, groups=None, enabled=None), dict(groups=[2, 0, 2])])
def test_omission_null_and_group_order_converge(harness, extra):
    harness.api.get_domains.return_value = {'domains': [record(groups=[0, 2])]}
    result = harness.run([dict(domain='example.com', type='deny', **extra)])
    assert not result.failed and not result.payload['changed']
    assert result.payload['domains'][0]['action'] == 'unchanged'
    assert_no_writes(harness)


@pytest.mark.parametrize('old_comment', [None, ''])
@pytest.mark.parametrize('check', [False, True])
def test_empty_comment_already_cleared_converges(harness, old_comment, check):
    harness.api.get_domains.return_value = {'domains': [record(comment=old_comment)]}
    result = harness.run([dict(domain='example.com', type='deny', comment='')], check=check)
    assert not result.failed and not result.payload['changed']
    row, = result.payload['domains']
    assert row['action'] == 'unchanged' and row['comment'] is None
    assert_no_writes(harness)


@pytest.mark.parametrize('check', [False, True])
@pytest.mark.parametrize('exists', [False, True])
def test_delete_or_absent_already(harness, check, exists):
    harness.api.get_domains.return_value = {'domains': [record()] if exists else []}
    result = harness.run([dict(domain='example.com', type='deny', state='absent', groups=['ignored'])], check=check)
    assert not result.failed and result.payload['changed'] is exists
    assert result.payload['domains'][0]['action'] == ('deleted' if exists else 'absent_already')
    if exists and not check:
        harness.api.delete_domain.assert_called_once_with('example.com', domain_type='deny', kind='exact')
    else:
        assert_no_writes(harness)


def test_identity_includes_type_and_kind(harness):
    harness.api.get_domains.return_value = {'domains': [record(type='allow'), record(kind='regex')]}
    result = harness.run()
    assert result.payload['domains'][0]['action'] == 'added'


@pytest.mark.parametrize('name,canonical', [('EXAMPLE.COM', 'example.com'), ('ä.com', 'xn--4ca.com')])
def test_exact_name_canonicalization(harness, name, canonical):
    harness.api.get_domains.return_value = {'domains': [record(domain=canonical)]}
    result = harness.run([dict(domain=name, type='deny')])
    assert not result.failed and not result.payload['changed']
    assert result.payload['domains'][0]['domain'] == canonical


def test_regex_identity_is_case_sensitive(harness):
    harness.api.get_domains.return_value = {'domains': [record(domain='EXAMPLE', kind='regex')]}
    result = harness.run([dict(domain='example', type='deny', kind='regex')])
    assert result.payload['domains'][0]['action'] == 'added'


@pytest.mark.parametrize('check', [False, True])
@pytest.mark.parametrize('bad_groups', [['missing'], ['0'], [True], [{}]])
def test_bad_group_in_later_entry_prevents_all_writes(harness, check, bad_groups):
    result = harness.run([dict(domain='first.example', type='allow'),
                          dict(domain='next.example', type='deny', groups=bad_groups)], check=check)
    assert result.failed and not result.payload['changed']
    assert result.payload['domains'] == []
    assert_no_writes(harness)


@pytest.mark.parametrize('response', [None, {}, {'domains': None}, {'error': 'read failed'},
                                      {'domains': [None]}, {'domains': [{}]},
                                      {'processed': {'errors': ['bad']}, 'domains': []},
                                      {'domains': [record(groups=None)]},
                                      {'domains': [record(groups=[True])]},
                                      {'domains': [record(enabled=None)]},
                                      {'domains': [record(comment=3)]},
                                      {'domains': [record(domain='')]},
                                      {'domains': [record(), record()]},
                                      {'domains': [record(type='block')]}])
@pytest.mark.parametrize('check', [False, True])
def test_domain_reads_fail_closed(harness, response, check):
    harness.api.get_domains.return_value = response
    result = harness.run(check=check)
    assert result.failed and not result.payload['changed']
    assert result.payload['response'] == response
    assert_no_writes(harness)
    harness.client.close_session.assert_called_once()


@pytest.mark.parametrize('response', [None, {}, {'groups': [{}]}, {'error': 'denied'}])
def test_bad_group_state_prevents_domain_discovery(harness, response):
    harness.client.group_management.get_groups.return_value = response
    result = harness.run()
    assert result.failed and not result.payload['changed']
    assert result.payload['response'] == response
    harness.api.get_domains.assert_not_called()
    assert_no_writes(harness)


@pytest.mark.parametrize('method', ['get_domains', 'add_domain', 'update_domain', 'delete_domain'])
def test_exceptions_retain_api_details(harness, method):
    error = PiHoleAPIError('denied', {'error': {'message': 'denied'}}, 403)
    getattr(harness.api, method).side_effect = error
    item = dict(domain='example.com', type='deny', comment='replace')
    if method in ('update_domain', 'delete_domain'):
        harness.api.get_domains.return_value = {'domains': [record()]}
    if method == 'delete_domain':
        item['state'] = 'absent'
    result = harness.run([item])
    assert result.failed and not result.payload['changed']
    assert result.payload['response'] == error.response and result.payload['status_code'] == 403
    harness.client.close_session.assert_called_once()


@pytest.mark.parametrize('action', ['add', 'update', 'delete'])
@pytest.mark.parametrize('response', [{'error': 'denied'}, {'processed': {'errors': ['invalid']}}])
def test_rejected_writes_do_not_mark_changed(harness, action, response):
    if action != 'add':
        harness.api.get_domains.return_value = {'domains': [record()]}
    getattr(harness.api, action + '_domain').return_value = response
    item = dict(domain='example.com', type='deny', comment='new')
    if action == 'delete':
        item['state'] = 'absent'
    result = harness.run([item])
    assert result.failed and not result.payload['changed'] and not result.payload['domains']
    assert result.payload['response'] == response


def test_partial_batch_failure_retains_completed_results(harness):
    harness.api.add_domain.side_effect = [{}, PiHoleAPIError('rejected', {'error': 'rejected'}, 200)]
    result = harness.run([dict(domain='first.example', type='allow'), dict(domain='second.example', type='deny')])
    assert result.failed and result.payload['changed']
    assert len(result.payload['domains']) == 1
    assert result.payload['domains'][0]['domain'] == 'first.example'
    assert result.payload['status_code'] == 200
    harness.client.actions.run_gravity.assert_not_called()


@pytest.mark.parametrize('items', [
    [dict(domain='', type='deny')], [dict(domain='  ', type='deny')],
    [dict(domain='example.com', type='block')], [dict(domain='example.com', type='deny', kind='wildcard')],
    [dict(domain='example.com')], [dict(type='deny')],
    [dict(domain='EXAMPLE.COM', type='deny'), dict(domain='example.com', type='deny')],
])
def test_bad_arguments_fail_before_auth(harness, items):
    result = harness.run(items)
    assert result.failed
    harness.factory.assert_not_called()


def test_missing_dependency_fails_before_auth(harness, monkeypatch):
    monkeypatch.setattr(domains, 'HAS_PIHOLE6API', False)
    result = harness.run()
    assert result.failed and not result.payload['changed']
    harness.factory.assert_not_called()
