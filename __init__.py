"""Hermes Virtue Office: local, fail-open lifecycle observer (Python stdlib only).

Hook contracts follow Hermes Pixel Office and Hermes Agent's PluginContext.
No model tools, prompt changes, raw arguments, tool results or approval controls.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
import json
import hashlib
import hmac
import secrets
from http.cookies import SimpleCookie
import logging
import mimetypes
import os
from pathlib import Path
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

VERSION = "0.2.0"
DEFAULT_PORT = 8114
WEB = Path(__file__).resolve().parent / "web"
logger = logging.getLogger("hermes.virtue-office")
_current_session = contextvars.ContextVar("virtue_session", default="")
_runtime = None
_runtime_lock = threading.Lock()
HOOKS = {
    "on_session_start": "session_start", "on_session_end": "session_end",
    "pre_tool_call": "tool_start", "post_tool_call": "tool_end",
    "subagent_start": "subagent_start", "subagent_stop": "subagent_stop",
    "pre_approval_request": "approval_request", "post_approval_response": "approval_response",
}


def short(value, limit=80):
    return " ".join(str(value or "").split())[:limit]


def activity_for(tool):
    tool = str(tool or "").lower()
    if any(x in tool for x in ("delegate", "subagent")):
        return "delegating"
    if any(x in tool for x in ("write", "patch", "edit", "create_file")):
        return "typing"
    if any(x in tool for x in ("web", "browser", "fetch", "search_query")):
        return "browsing"
    if any(x in tool for x in ("terminal", "exec", "shell", "python", "bash")):
        return "terminal"
    if any(x in tool for x in ("read", "search", "grep", "list", "memory")):
        return "reading"
    return "working"


class Store:
    """Atomic shared state across Hermes processes, with bounded event history."""

    def __init__(self, directory):
        self.directory = Path(directory).expanduser().resolve()
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.directory / "state.sqlite3"
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS agents (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS aliases (alias TEXT PRIMARY KEY, agent_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, data TEXT);
            """)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=0.05)
        try:
            with db:
                yield db
        finally:
            db.close()

    def apply(self, kind, kw, now=None):
        now = time.time() if now is None else now
        child = short(kw.get("child_session_id"), 200)
        sid = short(kw.get("session_id"), 200)
        alias = short(kw.get("session_key"), 200)
        if kind.startswith("subagent_"):
            sid = child or sid
        if not sid and not alias:
            sid = _current_session.get() if kind.startswith("approval_") else ""
        sid = sid or alias or f"process-{os.getpid()}"
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if alias and not kw.get("session_id"):
                row = db.execute("SELECT agent_id FROM aliases WHERE alias=?", (alias,)).fetchone()
                if row:
                    sid = row[0]
            if alias:
                db.execute("INSERT OR REPLACE INTO aliases VALUES (?, ?)", (alias, sid))
            row = db.execute("SELECT data FROM agents WHERE id=?", (sid,)).fetchone()
            a = json.loads(row[0]) if row else {
                "id": sid, "label": "Hermes " + sid[-6:], "kind": "main", "parent": "",
                "status": "idle", "activity": "", "tool": "", "platform": "",
                "first_seen": now, "updated_at": now, "tools_completed": 0, "errors": 0,
                "approval": False, "outcome": "", "pid": os.getpid(),
            }
            a["updated_at"] = now
            if kind == "session_start":
                a.update(status="idle", approval=False, tool="", activity="", outcome="")
                a["platform"] = short(kw.get("platform"), 30) or "hermes"
                a["label"] = a["platform"] + " · " + sid[-6:]
            elif kind in ("session_end", "subagent_stop"):
                a.update(status="done" if kind == "subagent_stop" else "gone", approval=False, tool="")
                if kind == "subagent_stop":
                    a["kind"] = "subagent"
                if kind == "session_end":
                    for ck, raw in db.execute("SELECT id,data FROM agents").fetchall():
                        ca = json.loads(raw)
                        if ca.get("parent") == sid and ca["status"] not in ("gone", "done"):
                            ca.update(status="done", approval=False, updated_at=now)
                            db.execute("UPDATE agents SET data=? WHERE id=?", (json.dumps(ca), ck))
            elif kind == "subagent_start":
                a.update(kind="subagent", parent=short(kw.get("parent_session_id"), 200), status="working")
                a["label"] = (short(kw.get("child_role"), 32) or "Subagent") + " · " + sid[-6:]
                a["activity"] = "thinking"
            elif kind == "tool_start":
                a["tool"] = short(kw.get("tool_name"))
                a["activity"] = activity_for(a["tool"])
                a["status"] = "waiting" if a["approval"] else "working"
                a["outcome"] = ""
            elif kind == "tool_end":
                a["tools_completed"] += 1
                a["status"] = "waiting" if a["approval"] else "thinking"
                if kw.get("status") == "error":
                    a["errors"] += 1
                    a["outcome"] = "error"
                else:
                    a["outcome"] = "ok"
                a["tool"] = ""
            elif kind == "approval_request":
                a.update(status="waiting", approval=True)
            elif kind == "approval_response":
                # Keep the real decision in Hermes; this hook only observes its outcome.
                denied = str(kw.get("choice", "")).lower() in ("deny", "denied", "timeout", "reject", "no")
                a.update(approval=False, status="thinking" if denied else "working", outcome="denied" if denied else "approved")
            db.execute("INSERT OR REPLACE INTO agents VALUES (?,?)", (sid, json.dumps(a)))
            event = {"event": kind, "agent_id": sid, "label": a["label"], "tool": a["tool"], "ts": now}
            db.execute("INSERT INTO events(ts,data) VALUES (?,?)", (now, json.dumps(event)))
            db.execute("DELETE FROM events WHERE seq <= (SELECT COALESCE(MAX(seq),0)-500 FROM events)")
            # Prune only old actors, never the latest state of a busy session.
            if kind == "session_start":
                for key, data in db.execute("SELECT id,data FROM agents").fetchall():
                    if now - json.loads(data)["updated_at"] > 86400:
                        db.execute("DELETE FROM agents WHERE id=?", (key,))
                        db.execute("DELETE FROM aliases WHERE agent_id=?", (key,))
        if kind in ("session_start", "tool_start"):
            _current_session.set(sid)

    def snapshot(self, now=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            rows = db.execute("SELECT data FROM agents").fetchall()
            events = [json.loads(r[0]) for r in db.execute("SELECT data FROM events ORDER BY seq DESC LIMIT 12")]
        agents = []
        for (raw,) in rows:
            a = json.loads(raw)
            age = now - a["updated_at"]
            if age > 86400 or (a["status"] in ("gone", "done") and age > 30):
                continue
            if a["status"] == "thinking" and age > 120:
                a["status"] = "idle"
            a["quiet"] = age > 300
            agents.append(a)
        agents.sort(key=lambda a: (a["first_seen"], a["id"]))
        return {"agents": agents, "events": events, "ts": now,
                "waiting": sum(a["approval"] for a in agents),
                "tools_completed": sum(a["tools_completed"] for a in agents)}


class OfficeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class OfficeAuth:
    """Server-side sessions. An unset password locks the office until configured."""
    lifetime = 8 * 60 * 60

    def __init__(self, password=None):
        if password is None:
            password = os.environ.get("VIRTUE_OFFICE_PASSWORD", "")
            password_file = os.environ.get("VIRTUE_OFFICE_PASSWORD_FILE")
            if password_file:
                password = Path(password_file).read_text().rstrip("\r\n")
        self.configured = bool(password)
        self.salt = secrets.token_bytes(32)
        self.digest = self.hash_password(password) if self.configured else b""
        self.key = secrets.token_bytes(32)
        self.sessions = {}
        self.attempts = []
        self.lock = threading.Lock()

    def hash_password(self, password):
        return hashlib.pbkdf2_hmac("sha256", password.encode(), self.salt, 600_000)

    def csrf_token(self):
        value = f"{int(time.time())}.{secrets.token_hex(24)}"
        return value + "." + hmac.new(self.key, value.encode(), "sha256").hexdigest()

    def valid_csrf(self, token, cookie):
        if not token or not hmac.compare_digest(token.encode(), cookie.encode()):
            return False
        try:
            stamp, nonce, signature = token.split(".")
            expected = hmac.new(self.key, f"{stamp}.{nonce}".encode(), "sha256").hexdigest()
            return 0 <= time.time() - int(stamp) < 900 and hmac.compare_digest(signature, expected)
        except (ValueError, TypeError):
            return False

    def login(self, password):
        now = time.time()
        with self.lock:
            self.attempts = [t for t in self.attempts if now - t < 60]
            if len(self.attempts) >= 5:
                return None, 429
            self.attempts.append(now)
            if not self.configured or not hmac.compare_digest(self.hash_password(password), self.digest):
                return None, 401
            token = secrets.token_urlsafe(32)
            self.sessions = {k: v for k, v in self.sessions.items() if v > now}
            self.sessions[hashlib.sha256(token.encode()).digest()] = now + self.lifetime
            return token, 200

    def authenticated(self, token):
        with self.lock:
            key = hashlib.sha256(token.encode()).digest()
            expires = self.sessions.get(key, 0)
            if expires <= time.time():
                self.sessions.pop(key, None)
                return False
            return True

    def logout(self, token):
        with self.lock:
            self.sessions.pop(hashlib.sha256(token.encode()).digest(), None)


def make_handler(store, mode="live", auth=None):
    auth = auth if auth is not None else OfficeAuth()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, code, body=b"", mime="text/plain; charset=utf-8", headers=()):
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; frame-ancestors 'self'")
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def cookie(self, name):
            try:
                cookies = SimpleCookie(self.headers.get("Cookie", ""))
                return cookies[name].value if name in cookies else ""
            except Exception:
                return ""

        def cookie_header(self, name, value, age):
            secure = "; Secure" if self.headers.get("X-Forwarded-Proto", "").lower() == "https" else ""
            return ("Set-Cookie", f"{name}={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}{secure}")

        def local_host(self):
            try:
                return urlsplit("//" + self.headers.get("Host", "")).hostname in ("127.0.0.1", "localhost", "::1")
            except ValueError:
                return False

        def login_page(self, status=200, message=""):
            if not auth.configured:
                self.reply(503, b"Office locked: configure VIRTUE_OFFICE_PASSWORD or VIRTUE_OFFICE_PASSWORD_FILE on the server, then restart.")
                return
            csrf = auth.csrf_token()
            body = (WEB / "login.html").read_text().replace("{{CSRF}}", csrf).replace("{{MESSAGE}}", message).encode()
            self.reply(status, body, "text/html; charset=utf-8", [self.cookie_header("virtue_csrf", csrf, 900)])

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            # Loopback bind + Host check + no CORS: local runtime metadata stays local.
            if not self.local_host():
                self.reply(403, b"Localhost only")
                return
            route = unquote(urlsplit(self.path).path)
            if route == "/login":
                self.login_page()
                return
            if route != "/health" and not auth.authenticated(self.cookie("virtue_session")):
                if route == "/" or route.endswith(".html"):
                    self.reply(302, headers=[("Location", "/login")])
                else:
                    self.reply(401, b'{"error":"login required"}', "application/json")
                return
            if route in ("/health", "/state"):
                payload = {"service": "hermes-virtue-office", "version": VERSION, "mode": mode}
                if route == "/state":
                    try:
                        payload.update(store.snapshot())
                    except sqlite3.Error:
                        self.reply(503, b'{"error":"state temporarily unavailable"}', "application/json")
                        return
                self.reply(200, json.dumps(payload).encode(), "application/json")
                return
            relative = "index.html" if route == "/" else route.lstrip("/")
            file = (WEB / relative).resolve()
            if not file.is_relative_to(WEB.resolve()) or not file.is_file() or any(p.startswith(".") for p in Path(relative).parts):
                self.reply(404, b"Not found")
                return
            mime = {".js": "text/javascript", ".glb": "model/gltf-binary"}.get(file.suffix) or mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            try:
                self.reply(200, file.read_bytes(), mime)
            except (OSError, BrokenPipeError):
                pass

        def do_POST(self):
            if not self.local_host():
                self.reply(403, b"Localhost only")
                return
            route = urlsplit(self.path).path
            if route == "/logout":
                if self.headers.get("X-Virtue-Logout") != "1":
                    self.reply(403, b"Invalid logout request")
                    return
                auth.logout(self.cookie("virtue_session"))
                self.reply(204, headers=[self.cookie_header("virtue_session", "", 0)])
                return
            if route != "/login":
                self.reply(405, b"Read-only observer; use Hermes to act on approvals")
                return
            if not auth.configured:
                self.login_page()
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if not 0 < length <= 4096:
                self.reply(400, b"Invalid login request")
                return
            self.connection.settimeout(5)
            try:
                fields = parse_qs(self.rfile.read(length).decode("utf-8"), max_num_fields=4)
                csrf = fields.get("csrf", [""])[0]
                password = fields.get("password", [""])[0]
            except (ValueError, UnicodeError, OSError):
                self.reply(400, b"Invalid login request")
                return
            if not auth.valid_csrf(csrf, self.cookie("virtue_csrf")):
                self.login_page(403, "Halaman login kedaluwarsa. Silakan coba lagi.")
                return
            token, status = auth.login(password)
            if not token:
                self.login_page(status, "Terlalu banyak percobaan. Tunggu satu menit." if status == 429 else "Password tidak sesuai. Silakan coba lagi.")
                return
            self.reply(303, headers=[("Location", "/"), self.cookie_header("virtue_session", token, auth.lifetime), self.cookie_header("virtue_csrf", "", 0)])

    return Handler


class Runtime:
    def __init__(self, directory, port=DEFAULT_PORT, mode="live", server_mode=None):
        self.store = Store(directory)
        self.port = port
        self.mode = mode
        self.server_mode = server_mode or os.environ.get("VIRTUE_OFFICE_SERVER_MODE", "embedded")
        if self.server_mode not in ("embedded", "external"):
            raise ValueError("server_mode must be embedded or external")
        self.server = None
        self.thread = None
        self.lock = threading.Lock()
        self.last_attempt = -float("inf")

    def ensure_server(self):
        # Retry on later events: a surviving Hermes process takes over the port
        # after its previous owner exits. Never probe/block in the agent hook.
        if self.server_mode == "external" or self.server or time.monotonic() - self.last_attempt < 3:
            return
        with self.lock:
            if self.server or time.monotonic() - self.last_attempt < 3:
                return
            self.last_attempt = time.monotonic()
            self.thread = threading.Thread(target=self._serve, name="virtue-office", daemon=True)
            self.thread.start()

    def _serve(self):
        try:
            server = OfficeServer(("127.0.0.1", self.port), make_handler(self.store, self.mode))
        except OSError as exc:
            logger.debug("virtue-office port unavailable; another process may own it: %s", exc)
            return
        self.server = server
        logger.info("Virtue Office at http://127.0.0.1:%s", server.server_port)
        try:
            server.serve_forever(poll_interval=.2)
        finally:
            server.server_close()
            self.server = None

    def observe(self, kind, **kw):
        try:
            self.store.apply(kind, kw)
            self.ensure_server()
        except Exception as exc:
            # Deliberately fail open. Do not log arguments or exception messages
            # which may contain host paths or data from the invoking tool.
            logger.warning("virtue-office observation skipped (%s)", type(exc).__name__)
        return None

    def close(self):
        server = self.server
        if server:
            server.shutdown()
        if self.thread:
            self.thread.join(timeout=2)


def runtime():
    global _runtime
    if _runtime is not None:
        return _runtime
    with _runtime_lock:
        if _runtime is None:
            port = DEFAULT_PORT
            server_mode = os.environ.get("VIRTUE_OFFICE_SERVER_MODE", "embedded")
            try:
                from hermes_cli.config import cfg_get, load_config
                configured = cfg_get(load_config(), "plugins", "entries", "virtue-office", "port")
                configured_mode = cfg_get(load_config(), "plugins", "entries", "virtue-office", "server_mode")
                if configured_mode is not None:
                    server_mode = str(configured_mode)
                if configured is not None:
                    port = int(configured)
                if not 1024 <= port <= 65535:
                    port = DEFAULT_PORT
            except (ImportError, TypeError, ValueError, OSError):
                pass
            home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
            _runtime = Runtime(home / "virtue-office", port, server_mode=server_mode)
    return _runtime


def register(ctx):
    for hook_name, event in HOOKS.items():
        def callback(_event=event, **kw):
            try:
                runtime().observe(_event, **kw)
            except Exception as exc:
                logger.warning("virtue-office unavailable (%s)", type(exc).__name__)
            return None
        ctx.register_hook(hook_name, callback)
    logger.info("virtue-office hooks registered; embedded mode starts a viewer on the first event, external mode uses a separate viewer")
