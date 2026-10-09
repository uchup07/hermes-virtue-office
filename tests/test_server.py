"""The independent viewer must outlive short-lived Hermes writers."""
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from http.cookiejar import CookieJar
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPCookieProcessor, Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

class StandaloneTests(unittest.TestCase):
    def test_viewer_starts_empty_and_survives_a_writer_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = {**os.environ, "VIRTUE_OFFICE_PASSWORD": "test-only-office", "VIRTUE_OFFICE_PASSWORD_FILE": ""}
            process = subprocess.Popen([sys.executable, str(ROOT/"serve.py"), "--port", str(port), "--data-dir", directory], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            base = f"http://127.0.0.1:{port}"
            try:
                for _ in range(100):
                    if process.poll() is not None:
                        self.fail(process.stderr.read().decode())
                    try:
                        with urlopen(base+"/health", timeout=.3) as response:
                            self.assertEqual(json.load(response)["mode"], "live")
                        break
                    except OSError:
                        time.sleep(.05)
                else:
                    self.fail("Viewer did not start without Hermes activity")
                opener = build_opener(HTTPCookieProcessor(CookieJar()))
                with opener.open(base+"/login") as response:
                    csrf = re.search(r'name="csrf" value="([^"]+)"', response.read().decode()).group(1)
                with opener.open(Request(base+"/login", data=urlencode({"csrf":csrf,"password":"test-only-office"}).encode())) as response:
                    self.assertEqual(response.status, 200)
                with opener.open(base+"/state") as response:
                    self.assertEqual(json.load(response)["agents"], [])
                # A separate short-lived process shares state, but owns no HTTP server.
                code = """
import importlib.util, sys
spec=importlib.util.spec_from_file_location('office',sys.argv[1])
office=importlib.util.module_from_spec(spec);spec.loader.exec_module(office)
runtime=office.Runtime(sys.argv[2],server_mode='external')
runtime.observe('session_start',session_id='writer')
runtime.observe('tool_start',session_id='writer',tool_name='read_file')
runtime.observe('session_end',session_id='writer')
assert runtime.server is None and runtime.thread is None
"""
                subprocess.run([sys.executable,"-c",code,str(ROOT/"__init__.py"),directory],check=True,timeout=10)
                self.assertIsNone(process.poll())
                with opener.open(base+"/state") as response:
                    state=json.load(response)
                    self.assertEqual(state["agents"][0]["status"],"gone")
                with urlopen(base+"/health") as response:
                    self.assertEqual(response.status,200)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait()
                errors=process.stderr.read().decode();process.stderr.close()
                self.assertEqual(process.returncode,0,errors)
