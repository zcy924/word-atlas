"""Personal Word Atlas sync. Standard library only; bind behind Caddy."""
import hashlib
import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time

COOKIE = "__Host-word-atlas-sync"
TTL = 30 * 86400
LIMIT = 8 * 1024 * 1024


class SyncDB:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS spaces(code TEXT PRIMARY KEY, salt TEXT, password TEXT);
                CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, code TEXT, expires INTEGER);
                CREATE TABLE IF NOT EXISTS snapshots(code TEXT, dataset TEXT, revision INTEGER,
                    payload TEXT, updated INTEGER, PRIMARY KEY(code, dataset));
            """)

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    @staticmethod
    def password(value, salt):
        return hashlib.pbkdf2_hmac("sha256", value.encode(), bytes.fromhex(salt), 600000).hex()

    def create(self, password):
        code = "".join(secrets.choice("23456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(12))
        salt = secrets.token_hex(16)
        digest = self.password(password, salt)
        with self.connect() as db:
            db.execute("INSERT INTO spaces VALUES(?,?,?)", (code, salt, digest))
        return code

    def login(self, code, password):
        with self.connect() as db:
            row = db.execute("SELECT salt,password FROM spaces WHERE code=?", (code,)).fetchone()
        digest = self.password(password, row[0] if row else "00" * 16)
        return bool(row and hmac.compare_digest(digest, row[1]))

    def new_session(self, code):
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires<?", (int(time.time()),))
            db.execute("INSERT INTO sessions VALUES(?,?,?)", (self.token_hash(token), code, int(time.time()) + TTL))
        return token

    @staticmethod
    def token_hash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def user(self, token):
        with self.connect() as db:
            row = db.execute("SELECT code FROM sessions WHERE token=? AND expires>?", (self.token_hash(token), int(time.time()))).fetchone()
        return row[0] if row else None

    def logout(self, token):
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE token=?", (self.token_hash(token),))

    def load(self, code, dataset):
        with self.connect() as db:
            row = db.execute("SELECT revision,payload,updated FROM snapshots WHERE code=? AND dataset=?", (code, dataset)).fetchone()
        return {"revision": row[0], "data": json.loads(row[1]), "updated": row[2]} if row else {"revision": 0, "data": None, "updated": None}

    def save(self, code, dataset, revision, data):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision FROM snapshots WHERE code=? AND dataset=?", (code, dataset)).fetchone()
            if (row[0] if row else 0) != revision:
                return False
            db.execute("INSERT OR REPLACE INTO snapshots VALUES(?,?,?,?,?)",
                       (code, dataset, revision + 1, json.dumps(data, ensure_ascii=False, allow_nan=False), int(time.time() * 1000)))
        return True


def make_handler(database, origin):
    attempts = []
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        timeout = 20

        def log_message(self, *_):
            pass  # Never log sync codes, cookies or learning data.

        def reply(self, status, value, cookie=None):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(body)

        def handle_request(self):
            if self.path == "/api/sync/health" and self.command == "GET":
                return self.reply(200, {"ok": True})
            if self.command != "GET":
                if self.headers.get("Origin") != origin or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    return self.reply(403, {"error": "请求来源无效。"})
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= LIMIT:
                        return self.reply(413, {"error": "同步数据大小超出限制。"})
                    body = json.loads(self.rfile.read(size), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                    if not isinstance(body, dict):
                        raise ValueError()
                except (ValueError, UnicodeDecodeError):
                    return self.reply(400, {"error": "同步数据格式无效。"})
            else:
                body = {}
            if self.path in ("/api/sync/create", "/api/sync/login") and self.command == "POST":
                # Global cap is intentional for this small personal service behind a proxy.
                with lock:
                    now = time.monotonic()
                    attempts[:] = [t for t in attempts if now - t < 60]
                    if len(attempts) >= 30:
                        return self.reply(429, {"error": "操作太频繁，请一分钟后重试。"})
                    attempts.append(now)
                password = body.get("password")
                if not isinstance(password, str) or not 12 <= len(password) <= 128:
                    return self.reply(400, {"error": "密码需要 12–128 个字符。"})
                code = body.get("code", "")
                if self.path.endswith("/create"):
                    code = database.create(password)
                elif not isinstance(code, str) or len(code) != 12 or not database.login(code, password):
                    return self.reply(401, {"error": "同步码或密码不正确。"})
                token = database.new_session(code)
                return self.reply(200, {"code": code}, f"{COOKIE}={token}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age={TTL}")
            cookies = SimpleCookie()
            cookies.load(self.headers.get("Cookie", ""))
            token = cookies[COOKIE].value if COOKIE in cookies else ""
            code = database.user(token)
            if not code:
                return self.reply(401, {"error": "请先连接同步空间。"})
            if self.path == "/api/sync/session" and self.command == "GET":
                return self.reply(200, {"code": code})
            if self.path == "/api/sync/logout" and self.command == "POST":
                database.logout(token)
                return self.reply(200, {"ok": True}, f"{COOKIE}=; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=0")
            prefix = "/api/sync/state/"
            if self.path.startswith(prefix):
                dataset = self.path[len(prefix):]
                if dataset != "word-atlas-open":
                    return self.reply(400, {"error": "当前仅支持开放词库同步。"})
                if self.command == "GET":
                    return self.reply(200, database.load(code, dataset))
                if self.command == "PUT":
                    data, revision = body.get("data"), body.get("revision")
                    progress = data.get("progress") if isinstance(data, dict) else None
                    if (type(revision) is not int or revision < 0 or not isinstance(progress, dict)
                            or data.get("app") != "word-atlas" or data.get("version") != 2
                            or progress.get("datasetId") != dataset or progress.get("version") != 2
                            or not isinstance(progress.get("cards"), dict) or not isinstance(data.get("settings"), dict)):
                        return self.reply(400, {"error": "学习数据格式无效。"})
                    progress["session"] = None
                    if not database.save(code, dataset, revision, data):
                        return self.reply(409, {"error": "另一台设备已更新，请选择要保留的版本。"})
                    return self.reply(200, {"revision": revision + 1, "updated": int(time.time() * 1000)})
            self.reply(404, {"error": "接口不存在。"})

        def do_GET(self):
            self.handle_request()

        do_POST = do_GET
        do_PUT = do_GET

    return Handler


if __name__ == "__main__":
    os.umask(0o077)
    path = Path(os.environ.get("SYNC_DB", "/var/lib/word-atlas-sync/sync.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 8322), make_handler(SyncDB(path), os.environ.get("SYNC_ORIGIN", "https://words.nivio.top")))
    server.serve_forever()
