import concurrent.futures
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from sync import COOKIE, SyncDB, make_handler
from http.server import ThreadingHTTPServer

ORIGIN = "https://words.nivio.top"
PASSWORD = "test-password-for-sync-only"
STATE = "/api/sync/state/word-atlas-open"


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "sync.sqlite3"
        self.db = SyncDB(self.path)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.db, ORIGIN))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, method="GET", body=None, cookie="", origin=ORIGIN):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=10)
        headers = {"Origin": origin, "Content-Type": "application/json", "Cookie": cookie}
        connection.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        result = (response.status, json.loads(response.read()), dict(response.getheaders()))
        connection.close()
        return result

    def create(self):
        status, data, headers = self.request("/api/sync/create", "POST", {"password": PASSWORD})
        self.assertEqual(status, 200)
        return data["code"], headers["Set-Cookie"].split(";")[0]

    def snapshot(self, bookmark="library"):
        return {"app": "word-atlas", "version": 2, "settings": {}, "progress": {
            "version": 2, "datasetId": "word-atlas-open", "cards": {}, "bookmarks": [bookmark], "session": {"secret": "device-only"}}}

    def test_credentials_and_cookie(self):
        code, cookie = self.create()
        self.assertEqual(len(code), 12)
        self.assertEqual(self.request("/api/sync/login", "POST", {"code": code, "password": "incorrect-password"})[0], 401)
        status, _, headers = self.request("/api/sync/login", "POST", {"code": code, "password": PASSWORD})
        self.assertEqual(status, 200)
        for flag in ("Secure", "HttpOnly", "SameSite=Strict", "Path=/"):
            self.assertIn(flag, headers["Set-Cookie"])
        self.assertNotIn(PASSWORD.encode(), self.path.read_bytes())
        self.assertNotIn(cookie.split("=", 1)[1].encode(), self.path.read_bytes())
        self.assertTrue(cookie.startswith(COOKIE + "="))

    def test_five_character_password_and_length_boundaries(self):
        for password in ("1234", "x" * 129):
            self.assertEqual(self.request("/api/sync/create", "POST", {"password": password})[0], 400)
        status, data, _ = self.request("/api/sync/create", "POST", {"password": "12345"})
        self.assertEqual(status, 200)
        self.assertEqual(self.request("/api/sync/login", "POST", {"code": data["code"], "password": "12345"})[0], 200)
        self.assertEqual(self.request("/api/sync/login", "POST", {"code": data["code"], "password": "1234"})[0], 400)

    def test_isolation_persistence_and_device_only_session(self):
        code, a = self.create()
        _, b = self.create()
        self.assertEqual(self.request(STATE)[0], 401)
        self.assertEqual(self.request(STATE, "PUT", {"revision": 0, "data": self.snapshot()}, a)[0], 200)
        self.assertIsNone(self.request(STATE, cookie=b)[1]["data"])
        restored = SyncDB(self.path).load(code, "word-atlas-open")
        self.assertEqual(restored["revision"], 1)
        self.assertIsNone(restored["data"]["progress"]["session"])
        self.assertEqual(restored["data"]["progress"]["bookmarks"], ["library"])

    def test_two_devices_only_one_write_can_win(self):
        _, cookie = self.create()
        def save(word):
            return self.request(STATE, "PUT", {"revision": 0, "data": self.snapshot(word)}, cookie)[0]
        with concurrent.futures.ThreadPoolExecutor(2) as executor:
            results = list(executor.map(save, ("one", "two")))
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(self.request(STATE, cookie=cookie)[1]["revision"], 1)

    def test_logout_revokes_session_and_preserves_cloud_data(self):
        code, cookie = self.create()
        self.request(STATE, "PUT", {"revision": 0, "data": self.snapshot()}, cookie)
        self.assertEqual(self.request("/api/sync/logout", "POST", {}, cookie)[0], 200)
        self.assertEqual(self.request(STATE, cookie=cookie)[0], 401)
        self.assertEqual(self.db.load(code, "word-atlas-open")["revision"], 1)

    def test_cross_origin_and_malformed_writes_are_rejected(self):
        _, cookie = self.create()
        self.assertEqual(self.request(STATE, "PUT", {"revision": 0, "data": self.snapshot()}, cookie, "https://evil.example")[0], 403)
        self.assertEqual(self.request(STATE, "PUT", {"revision": True, "data": self.snapshot()}, cookie)[0], 400)
        self.assertEqual(self.request(STATE, "PUT", {"revision": 0, "data": {}}, cookie)[0], 400)
        self.assertEqual(self.request("/api/sync/state/private", cookie=cookie)[0], 400)
        self.assertEqual(self.request(STATE, cookie=cookie)[1]["revision"], 0)


if __name__ == "__main__":
    unittest.main()
