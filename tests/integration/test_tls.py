"""Exercise certificate validation with real requests against loopback HTTPS."""

import datetime
import ipaddress
import ssl
import threading
from http.server import ThreadingHTTPServer

import pytest
import requests
import urllib3
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from plugins.module_utils.client import PiHole6Client


@pytest.fixture
def endpoint(tmp_path, monkeypatch, json_http_handler):
    monkeypatch.setenv('NO_PROXY', '127.0.0.1')
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([
                x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path / 'ca.pem', tmp_path / 'key.pem'
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                         serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    calls = []

    class Handler(json_http_handler):
        def do_POST(self):
            calls.append(self.path)
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            self.respond({'session': {'valid': True, 'validity': 300, 'sid': 'sid', 'csrf': 'csrf'}})

        def do_GET(self):
            calls.append(self.path)
            self.respond({'groups': []})

        def do_DELETE(self):
            calls.append(self.path)
            self.respond({})

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield 'https://127.0.0.1:{0}'.format(server.server_port), str(cert_path), calls
    server.shutdown()
    server.server_close()
    thread.join()


def test_untrusted_certificate_rejected_before_password_sent(endpoint):
    url, _, calls = endpoint
    with pytest.raises(requests.exceptions.SSLError):
        PiHole6Client(url, 'secret')
    assert calls == []


def test_private_ca_validates_auth_read_and_logout(endpoint):
    url, ca_path, calls = endpoint
    client = PiHole6Client(url, 'secret', ca_path=ca_path)
    try:
        assert client.group_management.get_groups() == {'groups': []}
    finally:
        client.close_session()
    assert calls == ['/api/auth', '/api/groups', '/api/auth']


def test_explicit_insecure_opt_out_warns(endpoint):
    url, _, calls = endpoint
    with pytest.warns(urllib3.exceptions.InsecureRequestWarning):
        client = PiHole6Client(url, 'secret', validate_certs=False)
        client.close_session()
    assert calls == ['/api/auth', '/api/auth']
