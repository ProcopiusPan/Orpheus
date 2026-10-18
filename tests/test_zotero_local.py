"""No real Zotero or production credentials: exercise the shared auth contract."""
from contextlib import nullcontext
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("orpheus_zotero_local", ROOT / "plugins/orpheus/scripts/zotero_local.py")
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)


class Store:
    def __init__(self):
        self.values = {}
    def load(self, server_id):
        return self.values.get(server_id)
    def save(self, server_id, key):
        self.values[server_id] = key
    def delete(self, server_id):
        self.values.pop(server_id, None)
    def lock(self, server_id):
        return nullcontext()


class Server:
    def __init__(self, server_id="instance1", remember=True):
        self.id = server_id
        self.remember = remember
        self.key = "fixture-secret"
        self.grants = 0
        self.writes = 0
        self.deny = False
        self.always_401 = False
        self.write_status = 204

    def __call__(self, path, method, data, headers, timeout):
        if path == "/api/local/authorize":
            assert headers["Zotero-Server-ID"] == self.id
            assert data == {"appName": M.APP_NAME}
            self.grants += 1
            if self.deny:
                return 403, {}, {"denied": True}
            return 200, {}, {"key": self.key, "remember": self.remember}
        if method == "GET":
            assert "Zotero-API-Key" not in headers
            return 200, {"Zotero-Server-ID": self.id}, []
        self.writes += 1
        if self.always_401 or headers.get("Zotero-API-Key") != self.key:
            return 401, {}, "Unauthorized"
        return self.write_status, {}, None


def test_new_client_reuses_remembered_grant_without_authorize(capsys):
    store, server = Store(), Server()
    a = M.Client(store, server)
    assert not a.status()["credential_cached"]
    a.request("/api/users/0/collections/ABCDEFGH", "PATCH", {"version": 1, "name": "same"})
    b = M.Client(store, server)
    result = b.request("/api/users/0/collections/ABCDEFGH", "PATCH", {"version": 1, "name": "same"})
    assert server.grants == 1 and server.writes == 2
    assert result["auth_source"] == "credential_manager" and result["authorization_requests"] == 0
    assert server.key not in str(result) + capsys.readouterr().out


def test_status_and_reads_never_prompt():
    store, server = Store(), Server()
    c = M.Client(store, server)
    c.status()
    c.request("/api/users/0/collections")
    assert server.grants == 0


def test_server_identity_isolates_keys():
    store, a, b = Store(), Server("a"), Server("b")
    M.Client(store, a).obtain_key()
    other = M.Client(store, b)
    assert not other.status()["credential_cached"]
    other.obtain_key()
    assert a.grants == b.grants == 1 and set(store.values) == {"a", "b"}
    assert M.WindowsCredentials.target("a") != M.WindowsCredentials.target("b")


def test_rejected_cached_key_renews_once_then_other_client_reuses():
    store, server = Store(), Server()
    store.save(server.id, "revoked-key")
    c = M.Client(store, server)
    result = c.request("/api/users/0/items", "POST", [])
    assert result["http_status"] == 204 and server.grants == 1 and server.writes == 2
    M.Client(store, server).request("/api/users/0/items", "POST", [])
    assert server.grants == 1


def test_single_use_grant_is_never_persisted():
    store, server = Store(), Server(remember=False)
    c = M.Client(store, server)
    c.obtain_key()
    assert not store.values and c.auth_source == "single_use"


def test_deny_stops_without_repeat_or_write():
    store, server = Store(), Server()
    server.deny = True
    with pytest.raises(M.ZoteroError, match="AUTH_NOT_GRANTED"):
        M.Client(store, server).request("/api/users/0/items", "POST", [])
    assert server.grants == 1 and server.writes == 0 and not store.values


def test_persistent_401_stops_after_one_renewal():
    store, server = Store(), Server()
    store.save(server.id, "old-key")
    server.always_401 = True
    with pytest.raises(M.ZoteroError, match="AUTH_REJECTED"):
        M.Client(store, server).request("/api/users/0/items", "POST", [])
    assert server.grants == 1 and server.writes == 2


@pytest.mark.parametrize("status", [403, 412, 429, 500])
def test_non_auth_errors_do_not_prompt_again(status):
    store, server = Store(), Server()
    store.save(server.id, server.key)
    server.write_status = status
    result = M.Client(store, server).request("/api/users/0/items", "POST", [])
    assert result["http_status"] == status and server.grants == 0 and server.writes == 1


@pytest.mark.parametrize("path", ["https://evil.example/api/", "/api/local/authorize", "/api/local%2Fauthorize",
    "/api//local/authorize", "/api/local/../local/authorize", "/api/users/0/items?key=secret", "/connector/import"])
def test_cli_cannot_return_grant_or_send_key_to_unintended_endpoint(path):
    store, server = Store(), Server()
    c = M.Client(store, server)
    with pytest.raises(M.ZoteroError, match="INVALID_PATH"):
        c.request(path, "POST", {})
    assert server.grants == 0 and server.writes == 0


def test_reflected_key_is_redacted():
    store, server = Store(), Server()
    store.save(server.id, server.key)
    def send(path, method, data, headers, timeout):
        if method != "GET":
            return 400, {}, {"error": "reflected " + server.key}
        return server(path, method, data, headers, timeout)
    result = M.Client(store, send).request("/api/users/0/items", "POST", [])
    assert server.key not in str(result) and "[REDACTED]" in str(result)


def test_secure_store_failure_does_not_fall_back_to_plaintext():
    store, server = Store(), Server()
    def fail(server_id, key):
        raise M.ZoteroError("SECURE_STORE_WRITE_FAILED")
    store.save = fail
    with pytest.raises(M.ZoteroError, match="SECURE_STORE_WRITE_FAILED"):
        M.Client(store, server).request("/api/users/0/items", "POST", [])
    assert server.grants == 1 and server.writes == 0


def test_other_process_refreshed_credential_is_reused_after_401():
    store, server = Store(), Server()
    c = M.Client(store, server)
    c.key = "stale-in-memory"
    store.save(server.id, server.key)  # Another process already renewed it.
    result = c.request("/api/users/0/items", "POST", [])
    assert result["http_status"] == 204 and server.grants == 0 and server.writes == 2


def test_authorization_timeout_stops_without_automatic_repeat():
    store, server = Store(), Server()
    def send(path, method, data, headers, timeout):
        if path == "/api/local/authorize":
            server.grants += 1
            raise M.ZoteroError("AUTH_TIMEOUT")
        return server(path, method, data, headers, timeout)
    with pytest.raises(M.ZoteroError, match="AUTH_TIMEOUT"):
        M.Client(store, send).request("/api/users/0/items", "POST", [])
    assert server.grants == 1 and not store.values and server.writes == 0
