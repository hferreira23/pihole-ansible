"""Pi-hole API client with collection-controlled TLS and error handling."""

import warnings

try:
    import requests
    # Upstream suppresses certificate warnings at import time. Do not let that
    # side effect escape into this collection or the caller's process.
    with warnings.catch_warnings():
        from pihole6api.client import PiHole6Client as _UpstreamClient
    HAS_PIHOLE6API = True
except ImportError:
    _UpstreamClient = object
    HAS_PIHOLE6API = False


class PiHoleAPIError(Exception):
    """An HTTP or API-level failure returned by Pi-hole."""

    def __init__(self, message, response=None, status_code=None):
        super().__init__(message)
        self.response = response
        self.status_code = status_code


if HAS_PIHOLE6API:
    from pihole6api import client as _api

    class _Actions(_api.PiHole6Actions):
        def run_gravity(self, timeout=None):
            return self.connection.post("action/gravity", timeout=timeout)

    class _SecureConnection:
        def __init__(self, base_url, password, validate_certs=True, ca_path=None):
            self.base_url = base_url.rstrip("/") + "/api/"
            self.password = password
            self.validate_certs = validate_certs
            self.verify = ca_path if validate_certs and ca_path else validate_certs
            self.connection_timeout = 10
            self.session_id = self.csrf_token = self.validity = None
            self.session = requests.Session()
            try:
                self._authenticate()
            except Exception:
                self.session.close()
                raise

        def _auth_response(self, response):
            data = self._decode_response(response)
            session = data.get("session", {}) if isinstance(data, dict) else {}
            if not (session.get("valid") and session.get("validity", 0) > 0 and session.get("sid") and session.get("csrf")):
                raise PiHoleAPIError(session.get("message", "Invalid Pi-hole session"), data, response.status_code)
            self.session_id, self.csrf_token = session["sid"], session["csrf"]
            self.validity = session["validity"]

        def _authenticate(self):
            response = self.session.post(self.base_url + "auth", json={"password": self.password}, verify=self.verify, timeout=self.connection_timeout)
            self._auth_response(response)

        def _do_call(self, method, endpoint, params=None, data=None, files=None, is_binary=False, timeout=None):
            headers = {"X-FTL-SID": self.session_id, "X-FTL-CSRF": self.csrf_token}
            kwargs = dict(headers=headers, params=params, files=files, verify=self.verify,
                          timeout=self.connection_timeout if timeout is None else timeout)
            if files:
                kwargs["data"] = data
            elif data is not None:
                kwargs["json"] = data
            url = self.base_url + endpoint
            response = self.session.request(method, url, **kwargs)
            if response.status_code == 401:
                self._authenticate()
                kwargs["headers"] = {"X-FTL-SID": self.session_id, "X-FTL-CSRF": self.csrf_token}
                response = self.session.request(method, url, **kwargs)
            if is_binary:
                if response.status_code >= 400:
                    self._raise(response)
                return response.content
            return self._decode_response(response)

        def _decode_response(self, response):
            """Decode successful payloads and reject HTTP and embedded errors."""
            try:
                result = response.json() if response.content.strip() else {}
            except (ValueError, requests.exceptions.JSONDecodeError):
                result = response.text
            if response.status_code >= 400:
                self._raise(response, result)
            if isinstance(result, dict):
                err = result.get("error")
                processed = result.get("processed")
                errors = processed.get("errors") if isinstance(processed, dict) else None
                if "error" in result or errors:
                    raise PiHoleAPIError(str(err or errors), result, response.status_code)
            return result

        @staticmethod
        def _raise(response, result=None):
            if result is None:
                try:
                    result = response.json()
                except ValueError:
                    result = response.text
            detail = result.get("error", result) if isinstance(result, dict) else result
            raise PiHoleAPIError("Pi-hole API request failed: {}".format(detail), result, response.status_code)

        def get(self, endpoint, params=None, is_binary=False):
            return self._do_call("GET", endpoint, params=params, is_binary=is_binary)

        def post(self, endpoint, data=None, files=None, params=None, timeout=None):
            return self._do_call("POST", endpoint, params=params, data=data, files=files, timeout=timeout)

        def put(self, endpoint, data=None, params=None):
            return self._do_call("PUT", endpoint, params=params, data=data)

        def patch(self, endpoint, data=None, params=None):
            return self._do_call("PATCH", endpoint, params=params, data=data)

        def delete(self, endpoint, params=None, data=None):
            return self._do_call("DELETE", endpoint, params=params, data=data)

        def exit(self):
            try:
                return self.delete("auth")
            except (requests.exceptions.RequestException, PiHoleAPIError) as error:
                # Logout must not turn a successful mutation into a failure or
                # hide the original failure that triggered cleanup.
                return {"error": str(error)}
            finally:
                self.session_id = self.csrf_token = self.validity = None
                self.session.close()


    class PiHole6Client(_UpstreamClient):
        def __init__(self, base_url, password, validate_certs=True, ca_path=None):
            self.connection = _SecureConnection(base_url, password, validate_certs, ca_path)
            for attr, cls in (("metrics", _api.PiHole6Metrics), ("dns_control", _api.PiHole6DnsControl),
                              ("group_management", _api.PiHole6GroupManagement), ("domain_management", _api.PiHole6DomainManagement),
                              ("client_management", _api.PiHole6ClientManagement), ("list_management", _api.PiHole6ListManagement),
                              ("ftl_info", _api.PiHole6FtlInfo), ("config", _api.PiHole6Configuration),
                              ("network_info", _api.PiHole6NetworkInfo), ("actions", _Actions), ("dhcp", _api.PiHole6Dhcp)):
                setattr(self, attr, cls(self.connection))
else:
    class PiHole6Client:
        def __init__(self, *args, **kwargs):
            raise ImportError("pihole6api is required to use PiHole6Client")
