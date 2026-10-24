"""Exercise actual group/client PUT payloads against a local Pi-hole stand-in."""

import importlib
import json
import threading
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit

import pytest
from ansible.module_utils import basic


OMITTED = object()


class ModuleExit(BaseException):
    def __init__(self, failed, payload):
        self.failed = failed
        self.payload = payload


@pytest.fixture(params=['groups', 'clients'])
def endpoint(request, monkeypatch, json_http_handler):
    monkeypatch.setenv('NO_PROXY', '127.0.0.1')
    kind = request.param
    name = 'Existing' if kind == 'groups' else '192.0.2.0/24'
    group = dict(id=1, name='Existing', enabled=True, comment='keep me')
    client = dict(client='192.0.2.0/24', groups=[1], comment='keep me')
    record = group if kind == 'groups' else client
    writes = []

    class Handler(json_http_handler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            if self.path == '/api/auth':
                self.respond({'session': {'valid': True, 'validity': 300, 'sid': 'sid', 'csrf': 'csrf'}})
            else:
                self.respond({'error': 'unexpected POST'}, 400)

        def do_GET(self):
            resources = {'/api/groups': {'groups': [group]}, '/api/clients': {'clients': [client]}}
            resource = resources.get(urlsplit(self.path).path)
            self.respond(resource if resource is not None else {'error': 'not found'},
                         200 if resource is not None else 404)

        def do_PUT(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if unquote(urlsplit(self.path).path) != '/api/{0}/{1}'.format(kind, name):
                self.respond({'error': 'unexpected PUT'}, 400)
                return
            writes.append(payload)
            record.update(payload)
            self.respond({kind: [record]})

        def do_DELETE(self):
            self.respond({} if self.path == '/api/auth' else {'error': 'unexpected DELETE'})

    module = importlib.import_module('ansible_collections.hferreira23.pihole.plugins.modules.' + kind)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    thread.start()

    def terminate(failed):
        def finish(self, **payload):
            raise ModuleExit(failed, payload)
        return finish

    monkeypatch.setattr(basic.AnsibleModule, 'exit_json', terminate(False))
    monkeypatch.setattr(basic.AnsibleModule, 'fail_json', terminate(True))

    def run(comment=OMITTED, check=False):
        item = dict(name=name, state='present')
        if kind == 'groups':
            item['enabled'] = False
        else:
            item['groups'] = []
        if comment is not OMITTED:
            item['comment'] = comment
        args = dict(url='http://127.0.0.1:{0}'.format(server.server_port), password='test',
                    _ansible_check_mode=check, **{kind: [item]})
        monkeypatch.setattr(basic, '_load_params', lambda: args)
        with pytest.raises(ModuleExit) as result:
            module.main()
        assert not result.value.failed, result.value.payload
        return result.value.payload

    try:
        yield SimpleNamespace(run=run, kind=kind, record=record, writes=writes)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize('old_comment', ['keep me', None])
@pytest.mark.parametrize('comment', [OMITTED, None, '', 'replacement'], ids=['omitted', 'null', 'clear', 'replace'])
def test_comment_payload_preview_and_convergence(endpoint, comment, old_comment):
    endpoint.record['comment'] = old_comment
    expected = old_comment if comment is OMITTED or comment is None else comment
    preview = endpoint.run(comment, check=True)
    assert preview['changed'] and preview[endpoint.kind][0]['comment'] == expected
    assert endpoint.writes == []

    first = endpoint.run(comment)
    assert first['changed'] and first[endpoint.kind][0]['comment'] == expected
    assert len(endpoint.writes) == 1
    assert endpoint.writes[0]['comment'] == expected
    assert endpoint.record['comment'] == expected

    second = endpoint.run(comment)
    assert not second['changed']
    assert second[endpoint.kind][0]['state'] == 'unchanged'
    assert second[endpoint.kind][0]['comment'] == expected
    assert len(endpoint.writes) == 1
