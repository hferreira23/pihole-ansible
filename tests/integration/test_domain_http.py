"""Exercise the domains module and collection transport against loopback HTTP."""

import importlib
import json
import threading
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import quote, unquote, urlsplit

import pytest
from ansible.module_utils import basic


class ModuleExit(BaseException):
    def __init__(self, failed, payload):
        self.failed = failed
        self.payload = payload


@pytest.fixture
def domains_api(monkeypatch, json_http_handler):
    """A deterministic Pi-hole API stand-in; all module HTTP uses loopback."""
    monkeypatch.setenv('NO_PROXY', '127.0.0.1,localhost')
    groups = [dict(id=1, name='Existing', enabled=True, comment='group')]
    entries = []
    requests_seen = []
    rejected_write = None

    class Handler(json_http_handler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            requests_seen.append(('POST', self.path, json.loads(body) if body else None))
            if self.path == '/api/auth':
                self.respond({'session': {'valid': True, 'validity': 300, 'sid': 'sid', 'csrf': 'csrf'}})
            elif self.path.startswith('/api/domains/'):
                payload = json.loads(body)
                if rejected_write and len([r for r in requests_seen if r[0] in ('POST', 'PUT') and r[1] != '/api/auth']) > rejected_write[2]:
                    self.respond(rejected_write[0], rejected_write[1])
                    return
                _, _, _, domain_type, kind = self.path.split('/')
                entry = dict(domain=payload['domain'][0], type=domain_type, kind=kind,
                              **{k: payload[k] for k in ('comment', 'groups', 'enabled')})
                entry['comment'] = entry['comment'] or None
                entries.append(entry)
                self.respond({'domains': [entry]})
            else:
                self.respond({'error': 'unexpected POST'}, 400)

        def do_GET(self):
            requests_seen.append(('GET', self.path, None))
            path = urlsplit(self.path).path
            if path == '/api/groups':
                self.respond({'groups': groups})
            elif path == '/api/domains':
                self.respond({'domains': entries})
            else:
                self.respond({'error': 'not found'}, 404)

        def do_PUT(self):
            payload = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
            requests_seen.append(('PUT', self.path, payload))
            if rejected_write and len([r for r in requests_seen if r[0] in ('POST', 'PUT') and r[1] != '/api/auth']) > rejected_write[2]:
                self.respond(rejected_write[0], rejected_write[1])
                return
            path = urlsplit(self.path).path
            bits = path.split('/')
            if len(bits) != 6 or bits[1:3] != ['api', 'domains']:
                self.respond({'error': 'unexpected PUT'}, 400)
                return
            identity = (unquote(bits[5]), bits[3], bits[4])
            entry = next((x for x in entries if (x['domain'], x['type'], x['kind']) == identity), None)
            if entry is None:
                self.respond({'error': 'missing domain'}, 404)
                return
            # Pi-hole stores empty comment strings as SQL NULL and returns null.
            entry.update(comment=payload['comment'] or None, groups=payload['groups'], enabled=payload['enabled'])
            self.respond({'domains': [entry]})

        def do_DELETE(self):
            requests_seen.append(('DELETE', self.path, None))
            if self.path == '/api/auth':
                self.respond({})
                return
            path = urlsplit(self.path).path
            bits = path.split('/')
            if len(bits) != 6 or bits[1:3] != ['api', 'domains']:
                self.respond({'error': 'unexpected DELETE'}, 400)
                return
            identity = (unquote(bits[5]), bits[3], bits[4])
            entries[:] = [x for x in entries if (x['domain'], x['type'], x['kind']) != identity]
            self.send_response(204)
            self.end_headers()

    module = importlib.import_module('ansible_collections.hferreira23.pihole.plugins.modules.domains')
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    thread.start()

    def terminate(failed):
        def finish(self, **payload):
            raise ModuleExit(failed, payload)
        return finish

    monkeypatch.setattr(basic.AnsibleModule, 'exit_json', terminate(False))
    monkeypatch.setattr(basic.AnsibleModule, 'fail_json', terminate(True))

    def run(items, check=False):
        args = dict(url='http://127.0.0.1:{0}'.format(server.server_port), password='test',
                    _ansible_check_mode=check, domains=items)
        monkeypatch.setattr(basic, '_load_params', lambda: args)
        with pytest.raises(ModuleExit) as result:
            module.main()
        return result.value

    api = SimpleNamespace(run=run, entries=entries, groups=groups, requests=requests_seen,
                          set_rejected=lambda response, status, after=0: _set_rejection(response, status, after))

    def _set_rejection(response, status, after):
        nonlocal rejected_write
        rejected_write = (response, status, after)

    try:
        yield api
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize('domain_type', ['allow', 'deny'])
@pytest.mark.parametrize('kind', ['exact', 'regex'])
def test_crud_converges_for_each_type_and_kind(domains_api, domain_type, kind):
    domain = 'item.example' if kind == 'exact' else r'(^|\.)item\.example$'
    item = dict(domain=domain, type=domain_type, kind=kind)
    added = domains_api.run([item])
    assert not added.failed, added.payload
    assert added.payload['changed']
    assert added.payload['domains'][0]['action'] == 'added'
    assert domains_api.entries[0] == dict(domain=domain, type=domain_type, kind=kind,
                                          comment=None, groups=[], enabled=True)

    converged = domains_api.run([item])
    assert not converged.failed, converged.payload
    assert not converged.payload['changed']
    assert converged.payload['domains'][0]['action'] == 'unchanged'

    updated = domains_api.run([dict(item, enabled=False)])
    assert not updated.failed, updated.payload
    assert updated.payload['domains'][0]['action'] == 'updated'
    assert updated.payload['changed'] and domains_api.entries[0]['enabled'] is False
    assert domains_api.entries[0]['comment'] is None and domains_api.entries[0]['groups'] == []
    stable = domains_api.run([dict(item, enabled=False)])
    assert not stable.failed and not stable.payload['changed']

    deleted = domains_api.run([dict(item, state='absent')])
    assert not deleted.failed, deleted.payload
    assert deleted.payload['changed'] and deleted.payload['domains'][0]['action'] == 'deleted'
    assert domains_api.entries == []
    assert sum(1 for method, path, _ in domains_api.requests if method == 'DELETE' and path == '/api/auth') == 5
    assert not any('gravity' in path for _, path, _ in domains_api.requests)


def test_check_mode_reads_authenticates_and_logs_out_without_writes(domains_api):
    domains_api.entries.append(dict(domain='exists.example', type='allow', kind='exact',
                                    comment='kept', groups=[1], enabled=True))
    result = domains_api.run([dict(domain='exists.example', type='allow', enabled=False)], check=True)
    assert not result.failed, result.payload
    assert result.payload['changed']
    assert result.payload['domains'][0]['action'] == 'updated'
    assert result.payload['domains'][0]['comment'] == 'kept'
    assert result.payload['domains'][0]['groups'] == [1]
    assert not any(method in ('POST', 'PUT') and path != '/api/auth' for method, path, _ in domains_api.requests)
    assert ('DELETE', '/api/auth', None) in domains_api.requests
    assert domains_api.entries[0]['enabled'] is True
    assert not any('gravity' in path for _, path, _ in domains_api.requests)


@pytest.mark.parametrize('fields,expected', [
    ({'enabled': False}, dict(comment='keep', groups=[1], enabled=False)),
    ({'comment': ''}, dict(comment=None, groups=[1], enabled=True)),
    ({'groups': []}, dict(comment='keep', groups=[], enabled=True)),
])
def test_effective_fields_preserved_or_explicitly_cleared(domains_api, fields, expected):
    domains_api.entries.append(dict(domain='keep.example', type='deny', kind='exact',
                                    comment='keep', groups=[1], enabled=True))
    result = domains_api.run([dict(domain='keep.example', type='deny', **fields)])
    assert not result.failed, result.payload
    assert result.payload['changed']
    put = next(payload for method, path, payload in domains_api.requests if method == 'PUT')
    assert {key: put[key] for key in expected} == expected
    assert {key: domains_api.entries[0][key] for key in expected} == expected


@pytest.mark.parametrize('domain_type', ['allow', 'deny'])
@pytest.mark.parametrize('kind', ['exact', 'regex'])
def test_clear_comment_normalizes_to_null_and_converges(domains_api, domain_type, kind):
    domain = 'clear.example' if kind == 'exact' else r'^clear\.example$'
    domains_api.entries.append(dict(domain=domain, type=domain_type, kind=kind,
                                    comment='clear me', groups=[1], enabled=False))
    item = dict(domain=domain, type=domain_type, kind=kind, comment='')
    first = domains_api.run([item])
    assert not first.failed and first.payload['changed']
    assert domains_api.entries[0]['comment'] is None
    second = domains_api.run([item])
    preview = domains_api.run([item], check=True)
    assert not second.failed and not second.payload['changed']
    assert not preview.failed and not preview.payload['changed']
    assert sum(method == 'PUT' for method, _, _ in domains_api.requests) == 1


@pytest.mark.parametrize('verb', ['PUT', 'DELETE'])
@pytest.mark.parametrize('domain', [r'a/b?c#d%e+f\\.example', '.', '..'])
def test_regex_path_is_quoted_exactly_and_server_decodes_identity(domains_api, verb, domain):
    domains_api.entries.append(dict(domain=domain, type='deny', kind='regex', comment='old', groups=[1], enabled=True))
    item = dict(domain=domain, type='deny', kind='regex', enabled=False)
    result = domains_api.run([item] if verb == 'PUT' else [dict(item, state='absent')])
    assert not result.failed, result.payload
    request = next((method, path) for method, path, _ in domains_api.requests if method == verb)
    assert request[1] == '/api/domains/deny/regex/' + quote(domain, safe='')
    assert unquote(request[1].rsplit('/', 1)[1]) == domain


@pytest.mark.parametrize('response,status', [({'error': 'write rejected'}, 409), ({'processed': {'errors': ['rejected']}}, 200)])
def test_rejected_write_returns_details_and_does_not_claim_change(domains_api, response, status):
    domains_api.set_rejected(response, status)
    result = domains_api.run([dict(domain='new.example', type='allow')])
    assert result.failed
    assert result.payload['changed'] is False
    assert result.payload['status_code'] == status
    assert result.payload['response'] == response
    assert domains_api.entries == []


def test_later_failure_retains_successful_partial_batch(domains_api):
    domains_api.set_rejected({'error': 'later rejected'}, 422, after=1)
    failed = domains_api.run([dict(domain='first.example', type='allow'),
                              dict(domain='second.example', type='allow')])
    assert failed.failed and failed.payload['changed'] is True
    assert [entry['domain'] for entry in domains_api.entries] == ['first.example']
    assert failed.payload['domains'][0]['domain'] == 'first.example'
    assert failed.payload['status_code'] == 422
