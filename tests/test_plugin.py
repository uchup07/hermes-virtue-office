import importlib.util
import json
import multiprocessing
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen, build_opener, HTTPCookieProcessor
from urllib.error import HTTPError
from urllib.parse import urlencode
from http.cookiejar import CookieJar
import re

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("virtue_plugin", ROOT / "__init__.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


def write_from_process(directory, suffix):
    store = plugin.Store(directory)
    store.apply("session_start", {"session_id": f"session-{suffix}"})
    for _ in range(5):
        store.apply("tool_end", {"session_id": f"session-{suffix}"})


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = plugin.Store(self.temp.name)
        plugin._current_session.set("")

    def tearDown(self):
        self.temp.cleanup()

    def emit(self, event, **kw):
        self.store.apply(event, {"session_id": "main", **kw}, now=100)

    def agent(self, key="main", now=101):
        return next(a for a in self.store.snapshot(now)["agents"] if a["id"] == key)

    def test_session_tool_and_error_lifecycle(self):
        self.emit("session_start", platform="cli")
        self.emit("tool_start", tool_name="write_file")
        self.assertEqual(self.agent()["activity"], "typing")
        self.emit("tool_end", status="error", error_message="secret should not persist")
        self.assertEqual(self.agent()["tools_completed"], 1)
        self.assertEqual(self.agent()["errors"], 1)
        self.assertEqual(self.agent()["status"], "thinking")
        self.emit("session_end")
        self.assertEqual(self.agent()["status"], "gone")
        self.assertEqual(self.store.snapshot(131)["agents"], [])

    def test_subagent_parent_and_session_end_cascade(self):
        self.emit("session_start")
        self.store.apply("subagent_start", {"parent_session_id": "main", "child_session_id": "child", "child_role": "Reviewer"}, 100)
        self.store.apply("tool_start", {"session_id": "child", "tool_name": "read_file"}, 101)
        child = self.agent("child")
        self.assertEqual(child["kind"], "subagent")
        self.assertEqual(child["parent"], "main")
        self.assertEqual(child["activity"], "reading")
        self.emit("session_end")
        self.assertEqual(self.agent("child")["status"], "done")

    def test_subagent_stop_without_start(self):
        self.store.apply("subagent_stop", {"child_session_id": "child"}, 100)
        self.assertEqual(self.agent("child")["status"], "done")
        self.assertEqual(self.agent("child")["kind"], "subagent")

    def test_approval_survives_tool_completion(self):
        self.emit("tool_start", tool_name="terminal")
        self.emit("approval_request")
        self.emit("tool_end")
        self.assertEqual(self.agent()["status"], "waiting")
        self.assertTrue(self.agent()["approval"])
        self.emit("approval_response", choice="deny")
        self.assertEqual(self.agent()["status"], "thinking")
        self.assertFalse(self.agent()["approval"])
        self.assertEqual(self.agent()["outcome"], "denied")

    def test_session_key_alias(self):
        self.emit("session_start", session_key="gateway:room:1")
        self.store.apply("approval_request", {"session_key": "gateway:room:1"}, 100)
        self.assertEqual(len(self.store.snapshot(101)["agents"]), 1)
        self.assertTrue(self.agent()["approval"])

    def test_concurrent_thread_approval_attribution(self):
        barrier = threading.Barrier(2)
        def worker(name):
            self.store.apply("tool_start", {"session_id": name, "tool_name": "terminal"}, 100)
            barrier.wait()
            self.store.apply("approval_request", {}, 100)
        threads = [threading.Thread(target=worker, args=(n,)) for n in ("a", "b")]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(self.store.snapshot(101)["waiting"], 2)

    def test_no_raw_content_persisted(self):
        secret = "DO_NOT_STORE_123456"
        self.emit("session_start")
        self.emit("tool_start", tool_name="terminal", args={"command": secret})
        self.emit("approval_request", command=secret, description=secret)
        self.emit("tool_end", error_message=secret, result=secret, status="error")
        self.store.apply("subagent_start", {"child_session_id":"child","child_goal":secret},100)
        with self.store.connect() as db:
            content = str(db.execute("SELECT data FROM agents").fetchall()) + str(db.execute("SELECT data FROM events").fetchall())
        self.assertNotIn(secret, content)

    def test_bounded_history_keeps_agent_identity(self):
        self.store.apply("subagent_start", {"child_session_id":"child","parent_session_id":"main","child_role":"Reviewer"},100)
        for i in range(510):
            self.store.apply("tool_end", {"session_id":"child"},100+i)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0],500)
        self.assertEqual(self.agent("child",611)["kind"],"subagent")
        self.assertEqual(self.agent("child",611)["tools_completed"],510)

    def test_multiple_processes_share_database(self):
        ctx=multiprocessing.get_context("spawn")
        processes=[ctx.Process(target=write_from_process,args=(self.temp.name,i)) for i in range(3)]
        for p in processes:p.start()
        for p in processes:p.join(10);self.assertEqual(p.exitcode,0)
        state=self.store.snapshot()
        self.assertEqual(len(state["agents"]),3)
        self.assertEqual(state["tools_completed"],15)

    def test_long_running_tool_is_not_marked_idle(self):
        self.emit("tool_start",tool_name="terminal")
        self.assertEqual(self.agent(now=1000)["status"],"working")
        self.assertTrue(self.agent(now=1000)["quiet"])

    def test_all_hooks_fail_open(self):
        callbacks={}
        class Context:
            def register_hook(self,name,fn):callbacks[name]=fn
        plugin.register(Context())
        self.assertEqual(set(callbacks),set(plugin.HOOKS))
        with patch.object(plugin,"runtime",side_effect=RuntimeError("secret")):
            for callback in callbacks.values():self.assertIsNone(callback(session_id="main"))

    def test_external_mode_records_without_starting_a_web_server(self):
        runtime = plugin.Runtime(self.temp.name, server_mode="external")
        runtime.observe("session_start", session_id="outside")
        runtime.observe("tool_start", session_id="outside", tool_name="read_file")
        self.assertIsNone(runtime.thread)
        self.assertIsNone(runtime.server)
        self.assertEqual(runtime.store.snapshot()["agents"][0]["activity"], "reading")

    def test_locked_database_does_not_veto_tools(self):
        runtime=plugin.Runtime(self.temp.name)
        lock=sqlite3.connect(self.store.path)
        lock.execute("BEGIN IMMEDIATE")
        try:
            started=time.monotonic()
            self.assertIsNone(runtime.observe("tool_start",session_id="main",tool_name="terminal"))
            self.assertLess(time.monotonic()-started,.5)
        finally:lock.rollback();lock.close()


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=plugin.Store(self.temp.name)
        self.auth=plugin.OfficeAuth("test-office-password")
        self.token,_=self.auth.login("test-office-password")
        self.server=plugin.OfficeServer(("127.0.0.1",0),plugin.make_handler(self.store, auth=self.auth))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f"http://127.0.0.1:{self.server.server_port}"

    def open(self, request):
        request = Request(request) if isinstance(request, str) else request
        request.add_header("Cookie", "virtue_session=" + self.token)
        return urlopen(request)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def test_state_health_and_assets(self):
        self.store.apply("session_start",{"session_id":"main"})
        with self.open(self.base+"/state") as r:
            state=json.load(r);self.assertEqual(state["service"],"hermes-virtue-office");self.assertEqual(state["mode"],"live");self.assertEqual(len(state["agents"]),1)
            self.assertIsNone(r.headers.get("Access-Control-Allow-Origin"))
        for route,mime in [("/","text/html"),("/app.js","text/javascript"),("/assets/01_Manager_Navy.glb","model/gltf-binary")]:
            with self.open(self.base+route) as r:self.assertIn(mime,r.headers["Content-Type"]);self.assertTrue(r.read())

    def test_no_state_mutation_or_path_escape(self):
        for route in ("/../__init__.py","/%2e%2e/__init__.py","/.git/config"):
            with self.assertRaises(HTTPError) as ctx:self.open(self.base+route)
            self.assertEqual(ctx.exception.code,404);ctx.exception.close()
        with self.assertRaises(HTTPError) as ctx:self.open(Request(self.base+"/approve",data=b'{}'))
        self.assertEqual(ctx.exception.code,405);ctx.exception.close()

    def test_foreign_host_rejected(self):
        with self.assertRaises(HTTPError) as ctx:self.open(Request(self.base+"/state",headers={"Host":"attacker.example"}))
        self.assertEqual(ctx.exception.code,403);ctx.exception.close()

    def test_follower_takes_over_after_server_exit(self):
        port=self.server.server_port
        follower=plugin.Runtime(self.temp.name,port)
        follower.ensure_server();follower.thread.join(2)
        self.assertIsNone(follower.server)
        self.server.shutdown();self.server.server_close();self.thread.join()
        follower.last_attempt=-float('inf');follower.ensure_server()
        for _ in range(100):
            if follower.server:break
            time.sleep(.01)
        try:
            self.assertIsNotNone(follower.server)
            with self.open(self.base+"/health") as r:self.assertEqual(json.load(r)["service"],"hermes-virtue-office")
        finally:follower.close()


    def test_auth_blocks_html_state_and_assets(self):
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        for route in ("/", "/playground.html"):
            with opener.open(self.base + route) as response:
                self.assertTrue(response.url.endswith("/login"))
                self.assertIn(b"PASSWORD KANTOR", response.read())
        for route in ("/state", "/app.js", "/assets/01_Manager_Navy.glb"):
            with self.assertRaises(HTTPError) as ctx:
                urlopen(self.base + route)
            self.assertEqual(ctx.exception.code, 401)
            ctx.exception.close()

    def test_login_wrong_password_success_and_logout(self):
        jar = CookieJar()
        opener = build_opener(HTTPCookieProcessor(jar))
        with opener.open(self.base + "/login") as response:
            csrf = re.search(r'name="csrf" value="([^"]+)"', response.read().decode()).group(1)
        with self.assertRaises(HTTPError) as ctx:
            opener.open(Request(self.base + "/login", data=urlencode({"csrf": csrf, "password": "wrong"}).encode()))
        self.assertEqual(ctx.exception.code, 401)
        csrf = re.search(r'name="csrf" value="([^"]+)"', ctx.exception.read().decode()).group(1)
        ctx.exception.close()
        with opener.open(Request(self.base + "/login", data=urlencode({"csrf": csrf, "password": "test-office-password"}).encode())) as response:
            self.assertEqual(response.url, self.base + "/")
            self.assertIn(b"Hermes Virtue Office", response.read())
        with opener.open(self.base + "/state") as response:
            self.assertEqual(json.load(response)["service"], "hermes-virtue-office")
        cookie = next(c for c in jar if c.name == "virtue_session")
        self.assertIn("HttpOnly", cookie._rest)
        self.assertEqual(cookie._rest["SameSite"], "Strict")
        with opener.open(Request(self.base + "/logout", data=b"", headers={"X-Virtue-Logout": "1"})) as response:
            self.assertEqual(response.status, 204)
        self.assertFalse(self.auth.authenticated(cookie.value))
        with self.assertRaises(HTTPError) as ctx:
            opener.open(self.base + "/state")
        self.assertEqual(ctx.exception.code, 401)
        ctx.exception.close()

    def test_login_rejects_csrf_and_limits_attempts(self):
        with self.assertRaises(HTTPError) as ctx:
            urlopen(Request(self.base + "/login", data=b"password=test-office-password&csrf=invalid"))
        self.assertEqual(ctx.exception.code, 403)
        ctx.exception.close()
        for _ in range(4):
            self.assertEqual(self.auth.login("wrong")[1], 401)
        self.assertEqual(self.auth.login("test-office-password")[1], 429)
        with patch.object(plugin.time, "time", return_value=time.time()+61):
            self.assertEqual(self.auth.login("test-office-password")[1], 200)

    def test_session_expiry_and_unknown_cookie(self):
        self.assertFalse(self.auth.authenticated("invented"))
        with patch.object(plugin.time, "time", return_value=time.time()+self.auth.lifetime+1):
            self.assertFalse(self.auth.authenticated(self.token))

    def test_unconfigured_office_locks_instead_of_exposing_data(self):
        locked = plugin.OfficeAuth("")
        self.assertFalse(locked.configured)
        self.assertFalse(locked.authenticated(""))
        self.assertEqual(locked.login("anything")[1], 401)

    def test_https_proxy_sets_secure_cookie(self):
        with self.open(Request(self.base + "/login", headers={"X-Forwarded-Proto": "https"})) as response:
            self.assertIn("; Secure", response.headers["Set-Cookie"])


if __name__=="__main__":unittest.main()
