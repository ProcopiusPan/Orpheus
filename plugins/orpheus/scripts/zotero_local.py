"""Orpheus's Windows-local Zotero write authorization, shared across sessions.

No credentials in the plugin, project, stdout, argv or environment. Only the
official authorize endpoint may issue a key; Windows Credential Manager stores
remembered keys under a version-independent, Zotero-server-specific target.
"""
import argparse
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request


ORIGIN = "http://127.0.0.1:23119"
APP_NAME = "Orpheus Zotero"


class ZoteroError(Exception):
    pass


class WindowsCredentials:
    """Only accesses Orpheus's own generic credential for the specified server."""
    def __init__(self):
        if os.name != "nt":
            raise ZoteroError("SECURE_STORE_UNAVAILABLE: requires Windows Credential Manager")
        class Credential(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]
        self.Credential = Credential
        self.api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        pointer = ctypes.POINTER(Credential)
        self.api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(pointer)]
        self.api.CredReadW.restype = wintypes.BOOL
        self.api.CredWriteW.argtypes = [pointer, wintypes.DWORD]
        self.api.CredWriteW.restype = wintypes.BOOL
        self.api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self.api.CredDeleteW.restype = wintypes.BOOL
        self.api.CredFree.argtypes = [ctypes.c_void_p]
        self.api.CredFree.restype = None

    @staticmethod
    def target(server_id):
        digest = hashlib.sha256((ORIGIN + "/" + server_id).encode()).hexdigest()
        return "Orpheus/Zotero/LocalAPI/" + digest

    def load(self, server_id):
        pointer = ctypes.POINTER(self.Credential)()
        if not self.api.CredReadW(self.target(server_id), 1, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == 1168:
                return None
            raise ZoteroError("SECURE_STORE_READ_FAILED")
        try:
            blob = ctypes.string_at(pointer.contents.CredentialBlob, pointer.contents.CredentialBlobSize)
            try:
                saved = json.loads(blob.decode("utf-8"))
            except (ValueError, UnicodeError):
                raise ZoteroError("SECURE_STORE_INVALID") from None
            if saved.get("server_id") != server_id or not isinstance(saved.get("key"), str):
                raise ZoteroError("SECURE_STORE_INVALID")
            return saved["key"]
        finally:
            self.api.CredFree(pointer)

    def save(self, server_id, key):
        blob = json.dumps({"server_id": server_id, "key": key}).encode("utf-8")
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        credential = self.Credential()
        credential.Type = 1  # CRED_TYPE_GENERIC
        credential.TargetName = self.target(server_id)
        credential.Comment = "Orpheus Zotero official local API authorization"
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = buffer
        credential.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE: same user, future logons
        credential.UserName = APP_NAME
        if not self.api.CredWriteW(ctypes.byref(credential), 0):
            raise ZoteroError("SECURE_STORE_WRITE_FAILED")

    def delete(self, server_id):
        if not self.api.CredDeleteW(self.target(server_id), 1, 0) and ctypes.get_last_error() != 1168:
            raise ZoteroError("SECURE_STORE_DELETE_FAILED")

    @contextmanager
    def lock(self, server_id):
        # Serialize the cache check + authorize sequence across chat processes.
        api = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        api.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        api.CreateMutexW.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.WaitForSingleObject.restype = wintypes.DWORD
        api.ReleaseMutex.argtypes = [wintypes.HANDLE]
        api.ReleaseMutex.restype = wintypes.BOOL
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        api.CloseHandle.restype = wintypes.BOOL
        name = "Local\\" + self.target(server_id).replace("/", ".")
        handle = api.CreateMutexW(None, False, name)
        if not handle:
            raise ZoteroError("AUTH_LOCK_FAILED")
        acquired = False
        try:
            result = api.WaitForSingleObject(handle, 60000)
            if result not in (0, 0x80):
                raise ZoteroError("AUTH_BUSY: another Orpheus process is authorizing; retry later")
            acquired = True
            yield
        finally:
            if acquired:
                api.ReleaseMutex(handle)
            api.CloseHandle(handle)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward the authorization header to another URL.


def transport(path, method, data, headers, timeout):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    body = None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(ORIGIN + path, data=body, headers=headers, method=method)
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    except (TimeoutError, urllib.error.URLError) as exc:
        if path == "/api/local/authorize" and (isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError)):
            raise ZoteroError("AUTH_TIMEOUT: Zotero authorization was not completed; no automatic repeat") from None
        raise ZoteroError("ZOTERO_UNAVAILABLE: start Zotero and enable its Local API") from None
    except OSError:
        raise ZoteroError("ZOTERO_UNAVAILABLE: start Zotero and enable its Local API") from None
    with response:
        raw = response.read().decode("utf-8", errors="replace")
        try:
            value = json.loads(raw) if raw else None
        except ValueError:
            value = raw
        return response.status, dict(response.headers), value


class Client:
    def __init__(self, store=None, send=transport):
        self.store = store if store is not None else WindowsCredentials()
        self.send = send
        self.key = None
        self.authorization_requests = 0
        self.auth_source = "none"
        status, headers, _ = self.send("/api/users/0/items/top?limit=1", "GET", None,
                                       {"Zotero-API-Version": "3"}, 10)
        self.server_id = next((v for k, v in headers.items() if k.lower() == "zotero-server-id"), None)
        if status != 200 or not self.server_id:
            raise ZoteroError("LOCAL_API_UNAVAILABLE: Zotero 10+ with Local API enabled is required")

    def obtain_key(self, rejected=None):
        with self.store.lock(self.server_id):
            cached = self.store.load(self.server_id)
            if cached and cached != rejected:
                self.key = cached
                self.auth_source = "credential_manager"
                return
            if rejected and cached == rejected:
                self.store.delete(self.server_id)
            self.authorization_requests += 1
            print("Zotero authorization required: choose Always Allow to reuse across chats.", file=sys.stderr, flush=True)
            status, _, grant = self.send("/api/local/authorize", "POST", {"appName": APP_NAME},
                {"Zotero-Server-ID": self.server_id, "Zotero-API-Version": "3", "Content-Type": "application/json"}, 300)
            if status != 200 or not isinstance(grant, dict) or not isinstance(grant.get("key"), str):
                raise ZoteroError(f"AUTH_NOT_GRANTED (HTTP {status}); no automatic repeat")
            self.key = grant["key"]
            self.auth_source = "new_remembered" if grant.get("remember") is True else "single_use"
            if grant.get("remember") is True:
                self.store.save(self.server_id, self.key)

    def status(self):
        return {"server_id": self.server_id, "credential_cached": bool(self.store.load(self.server_id)),
                "store": "Windows Credential Manager", "key_validity": "not_checked"}

    def request(self, path, method="GET", data=None):
        parsed = urllib.parse.urlsplit(path)
        if (parsed.scheme or parsed.netloc or parsed.fragment or "%" in parsed.path or "\\" in path
                or "\r" in path or "\n" in path or "//" in parsed.path or not parsed.path.startswith("/api/")
                or parsed.path.startswith("/api/local/") or ".." in urllib.parse.unquote(parsed.path).split("/")):
            raise ZoteroError("INVALID_PATH: use a non-local /api/ endpoint on the fixed loopback server")
        if any(k.lower() in ("key", "api_key", "apikey") for k, _ in urllib.parse.parse_qsl(parsed.query)):
            raise ZoteroError("INVALID_PATH: do not pass credentials in a URL")
        method = method.upper()
        if method not in ("GET", "POST", "PATCH", "PUT", "DELETE"):
            raise ZoteroError("INVALID_METHOD")
        writing = method != "GET"
        if writing and not self.key:
            self.obtain_key()
        def call():
            headers = {"Zotero-API-Version": "3", "Zotero-Server-ID": self.server_id,
                       "Content-Type": "application/json"}
            if writing:
                headers["Zotero-API-Key"] = self.key
            return self.send(path, method, data, headers, 30)
        status, _, body = call()
        if writing and status == 401:
            # At most one reauthorization, only for an actually rejected key.
            self.obtain_key(rejected=self.key)
            status, _, body = call()
        # Never include secret response material (including reflected keys).
        if self.key:
            body = json.loads(json.dumps(body, ensure_ascii=False).replace(self.key, "[REDACTED]"))
        result = {"http_status": status, "server_id": self.server_id, "auth_source": self.auth_source,
                  "authorization_requests": self.authorization_requests, "body": body}
        if status == 401:
            raise ZoteroError("AUTH_REJECTED: stopped after one renewal; retry only after checking Zotero")
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Readiness + cached-key presence only; never prompts")
    commands.add_parser("authorize", help="Reuse cached key, or request and securely save a new grant")
    commands.add_parser("forget", help="Remove only Orpheus's cached credential for this Zotero instance")
    request = commands.add_parser("request", help="Official local API request using shared authorization")
    request.add_argument("method", choices=["GET", "POST", "PATCH", "PUT", "DELETE"])
    request.add_argument("path", help="/api/users/0/...; no arbitrary hosts or authorize endpoint")
    request.add_argument("--json-file", type=Path, help="JSON body file; no credentials")
    args = parser.parse_args()
    try:
        client = Client()
        if args.command == "status":
            result = client.status()
        elif args.command == "authorize":
            client.obtain_key()
            result = {**client.status(), "auth_source": client.auth_source,
                      "authorization_requests": client.authorization_requests}
        elif args.command == "forget":
            client.store.delete(client.server_id)
            result = {"status": "CACHED_CREDENTIAL_REMOVED", "zotero_grant_revoked": False}
        else:
            body = json.loads(args.json_file.read_text(encoding="utf-8-sig")) if args.json_file else None
            result = client.request(args.path, args.method, body)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("http_status", 200) >= 400 or (isinstance(result.get("body"), dict) and result["body"].get("failed")):
            return 1
        return 0
    except (ZoteroError, OSError, ValueError) as exc:
        # No traceback containing request headers, grants or credential blobs.
        print(json.dumps({"error": str(exc) if isinstance(exc, ZoteroError) else type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
