"""Reusable response handling for the loopback HTTP/HTTPS API fixtures."""

import json
from http.server import BaseHTTPRequestHandler

import pytest


@pytest.fixture
def json_http_handler():
    class JSONHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, data, status=200):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return JSONHandler
