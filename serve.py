#!/usr/bin/env python3
"""Standalone viewer and isolated demo; does not install or configure Hermes."""
import argparse
import importlib.util
import logging
from pathlib import Path
import tempfile
import threading
import time

spec = importlib.util.spec_from_file_location("virtue_office", Path(__file__).with_name("__init__.py"))
office = importlib.util.module_from_spec(spec)
spec.loader.exec_module(office)


def demo(runtime, stop):
    names = ["demo-manager-001", "demo-designer-005", "demo-developer-004", "demo-operations-005", "demo-analyst-002"]
    for sid, platform in zip(names, ["CLI", "Coding", "Research", "Operations", "Analytics"]):
        runtime.observe("session_start", session_id=sid, platform=platform)
    tools = ["terminal", "write_file", "web_search", "read_file", "patch"]
    tick = 0
    while not stop.wait(1):
        phase = tick % 48
        for i, sid in enumerate(names):
            if phase % 8 == i:
                runtime.observe("tool_start", session_id=sid, tool_name=tools[i])
            if phase % 8 == (i + 4) % 8:
                runtime.observe("tool_end", session_id=sid, tool_name=tools[i], status="ok")
        if phase == 8:
            runtime.observe("subagent_start", parent_session_id=names[1], child_session_id="demo-child-006", child_role="Reviewer")
            runtime.observe("tool_start", session_id="demo-child-006", tool_name="read_file")
        if phase == 12:
            runtime.observe("approval_request", session_id=names[0])
        if phase == 23:
            runtime.observe("approval_response", session_id=names[0], choice="once")
        if phase == 30:
            runtime.observe("subagent_stop", child_session_id="demo-child-006")
        tick += 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=office.DEFAULT_PORT)
    p.add_argument("--demo", action="store_true", help="Synthetic activity in a temporary isolated database")
    p.add_argument("--data-dir", type=Path, help="Use an explicit shared state directory")
    args = p.parse_args()
    if not 1024 <= args.port <= 65535:
        p.error("port must be between 1024 and 65535")
    if args.demo and args.data_dir:
        p.error("--demo uses temporary data; do not combine it with --data-dir")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    temp = tempfile.TemporaryDirectory(prefix="virtue-office-demo-") if args.demo else None
    directory = Path(temp.name) if temp else args.data_dir or Path(office.os.environ.get("HERMES_HOME", Path.home()/".hermes"))/"virtue-office"
    runtime = office.Runtime(directory, args.port, "demo" if args.demo else "live")
    # Standalone startup reports port conflicts immediately.
    server = office.OfficeServer(("127.0.0.1", args.port), office.make_handler(runtime.store, runtime.mode))
    runtime.server = server
    stop = threading.Event()
    feed = threading.Thread(target=demo, args=(runtime, stop), daemon=True) if args.demo else None
    if feed:
        feed.start()
    print(f"Virtue Office ({runtime.mode}): http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if feed:
            feed.join(timeout=2)
        server.server_close()
        if temp:
            temp.cleanup()


if __name__ == "__main__":
    main()
