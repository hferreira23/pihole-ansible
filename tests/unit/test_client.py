import importlib
import pytest


client_module = importlib.import_module("plugins.module_utils.client")


class Response:
    def __init__(self, status=200, payload=None, text=None, content=None):
        self.status_code = status
        self._payload = payload
        self.text = text if text is not None else ""
        self.content = content if content is not None else (b"x" if payload is not None or text else b"")

    def json(self):
        if self._payload is None:
            raise ValueError("not JSON")
        return self._payload


class Session:
    instances = []

    def __init__(self):
        self.calls = []
        self.closed = False
        self.responses = []
        self.__class__.instances.append(self)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return Response(payload={"session": {"valid": True, "validity": 10, "sid": "sid", "csrf": "csrf"}})

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0) if self.responses else Response(payload={})

    def close(self):
        self.closed = True


@pytest.fixture
def client(monkeypatch):
    Session.instances.clear()
    monkeypatch.setattr(client_module.requests, "Session", Session)
    instance = client_module.PiHole6Client("https://hole", "secret")
    yield instance
    if not Session.instances[-1].closed:
        instance.close_session()


def test_tls_auth_and_read_write(client):
    session = client.connection.session
    auth = session.calls[0]
    assert auth[2]["verify"] is True
    assert auth[2]["json"] == {"password": "secret"}
    session.responses = [Response(payload={"ok": True}), Response(payload={"ok": True})]
    assert client.connection.get("test", params={"a": 1}) == {"ok": True}
    assert client.connection.put("test", data={"v": 2}) == {"ok": True}
    assert session.calls[1][2]["headers"]["X-FTL-SID"] == "sid"
    assert session.calls[2][2]["json"] == {"v": 2}
    assert all(call[2]['verify'] is True for call in session.calls)


def test_ca_path_and_explicit_insecure_opt_out(monkeypatch):
    monkeypatch.setattr(client_module.requests, "Session", Session)
    secure = client_module.PiHole6Client("https://hole", "pw", ca_path="/ca.pem")
    insecure = client_module.PiHole6Client("https://hole", "pw", validate_certs=False, ca_path="ignored")
    assert Session.instances[-2].calls[0][2]["verify"] == "/ca.pem"
    assert Session.instances[-1].calls[0][2]["verify"] is False
    secure.close_session()
    insecure.close_session()
    assert all(call[2]['verify'] == '/ca.pem' for call in secure.connection.session.calls)
    assert all(call[2]['verify'] is False for call in insecure.connection.session.calls)


def test_reauth_once_and_logout(client):
    session = client.connection.session
    session.responses = [Response(status=401, payload={"error": "expired"}), Response(payload={"ok": 1}), Response(payload={})]
    assert client.connection.get("test") == {"ok": 1}
    assert [call[0] for call in session.calls].count("POST") == 2
    client.close_session()
    assert session.closed
    assert session.calls[-1][1].endswith("auth")
    assert all(call[2]['verify'] is True for call in session.calls)


@pytest.mark.parametrize("response, expected", [
    (Response(status=400, payload={"error": "bad request"}), {"error": "bad request"}),
    (Response(status=500, text="broken"), "broken"),
    (Response(status=403, payload={"message": "denied"}), {"message": "denied"}),
    (Response(payload={"error": "rejected"}), {"error": "rejected"}),
    (Response(payload={"processed": {"errors": ["invalid"]}}), {"processed": {"errors": ["invalid"]}}),
])
def test_errors_preserve_details(client, response, expected):
    client.connection.session.responses = [response]
    with pytest.raises(client_module.PiHoleAPIError) as error:
        client.connection.get("test")
    assert error.value.response == expected
    assert error.value.status_code == response.status_code


def test_success_empty_and_text(client):
    client.connection.session.responses = [Response(), Response(text="plain")]
    assert client.connection.get("empty") == {}
    assert client.connection.get("text") == "plain"


def test_each_client_has_independent_transport(monkeypatch):
    monkeypatch.setattr(client_module.requests, "Session", Session)
    one = client_module.PiHole6Client("https://one", "a")
    two = client_module.PiHole6Client("https://two", "b")
    assert one.connection is not two.connection
    assert one.connection.session is not two.connection.session
    one.close_session()
    two.close_session()


@pytest.mark.parametrize('response', [
    Response(status=403, payload={'error': {'message': 'bad password'}}),
    Response(payload={'session': {'valid': False, 'message': 'invalid'}}),
    Response(payload={'error': 'invalid', 'session': {'valid': True, 'validity': 10,
                                                    'sid': 'sid', 'csrf': 'csrf'}}),
    Response(text='not a session'),
])
def test_authentication_failure_retains_details_and_closes(monkeypatch, response):
    monkeypatch.setattr(client_module.requests, 'Session', Session)
    monkeypatch.setattr(Session, 'post', lambda *args, **kwargs: response)
    with pytest.raises(client_module.PiHoleAPIError) as error:
        client_module.PiHole6Client('https://hole', 'secret')
    assert error.value.response == (response._payload if response._payload is not None else response.text)
    assert Session.instances[-1].closed


def test_certificate_failure_closes_before_any_api_call(monkeypatch):
    monkeypatch.setattr(client_module.requests, 'Session', Session)

    def reject(*args, **kwargs):
        assert kwargs['verify'] is True
        raise client_module.requests.exceptions.SSLError('untrusted certificate')

    monkeypatch.setattr(Session, 'post', reject)
    with pytest.raises(client_module.requests.exceptions.SSLError):
        client_module.PiHole6Client('https://hole', 'secret')
    assert Session.instances[-1].closed
    assert Session.instances[-1].calls == []


def test_reauthentication_failure_is_not_treated_as_data(client):
    session = client.connection.session
    session.responses = [Response(status=401, payload={'error': 'expired'}),
                         Response(status=401, payload={'error': 'denied'})]
    with pytest.raises(client_module.PiHoleAPIError) as error:
        client.connection.put('lists', data={})
    assert error.value.status_code == 401
    assert error.value.response == {'error': 'denied'}


def test_logout_failure_does_not_mask_original_result(client):
    client.connection.session.responses = [Response(status=500, text='logout failed')]
    assert 'error' in client.close_session()
    assert client.connection.session.closed


@pytest.mark.parametrize('timeout', [60, 300])
def test_gravity_timeout_applies_only_to_its_request(client, timeout):
    session = client.connection.session
    client.actions.run_gravity(timeout=timeout)
    client.group_management.get_groups()
    client.close_session()
    assert [call[2]['timeout'] for call in session.calls] == [10, timeout, 10, 10]
    assert client.connection.connection_timeout == 10
    assert session.calls[1][1].endswith('/api/action/gravity')


def test_gravity_reauthentication_keeps_normal_auth_timeout(client):
    session = client.connection.session
    session.responses = [Response(status=401, payload={'error': 'expired'}), Response(payload={})]
    client.actions.run_gravity(timeout=300)
    client.close_session()
    assert [call[2]['timeout'] for call in session.calls] == [10, 300, 10, 300, 10]
    assert client.connection.connection_timeout == 10


def test_unconfigured_action_timeout_uses_connection_default(client):
    session = client.connection.session
    client.actions.run_gravity()
    client.actions.restart_dns()
    assert all(call[2]['timeout'] == 10 for call in session.calls)


def test_domains_reads_all_types_and_kinds(client):
    client.domain_management.get_domains()
    assert client.connection.session.calls[-1][1] == 'https://hole/api/domains'


@pytest.mark.parametrize('method', ['get_domain', 'update_domain', 'delete_domain'])
def test_domain_path_identity_is_encoded_without_changing_json(client, method):
    from urllib.parse import quote
    domain = r'(^|\.)ad/[a-z]+\?#%\.example$'
    getattr(client.domain_management, method)(domain, 'deny', 'regex')
    _, url, kwargs = client.connection.session.calls[-1]
    assert url == 'https://hole/api/domains/deny/regex/' + quote(domain, safe='')
    assert kwargs['verify'] is True
    if method == 'update_domain':
        assert kwargs['json']['kind'] == 'regex' and kwargs['json']['type'] == 'deny'
