#!/usr/bin/env python3
import argparse
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HOST = "127.0.0.1"
PORT = 8765

class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.commands = []
        self.results = {}
        self.clients = set()

    def enqueue(self, payload):
        command_id = uuid.uuid4().hex
        with self.lock:
            self.commands.append({"id": command_id, **payload})
        return command_id

    def next_command(self):
        with self.lock:
            return self.commands.pop(0) if self.commands else None

    def set_result(self, command_id, result):
        with self.lock:
            self.results[command_id] = result

    def get_result(self, command_id):
        with self.lock:
            return self.results.get(command_id)

STATE = State()

class Handler(BaseHTTPRequestHandler):
    server_version = "localAI-browser-agent/0.1"

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json(200, {"ok": True, "service": "localAI-browser-agent", "port": PORT, "clients": len(STATE.clients)})
            return
        if path == "/next":
            client_id = self.headers.get("X-Client-Id", "unknown")
            with STATE.lock:
                STATE.clients.add(client_id)
            self._send_json(200, {"command": STATE.next_command()})
            return
        if path.startswith("/result/"):
            result = STATE.get_result(path.rsplit("/", 1)[-1])
            self._send_json(200, result) if result else self._send_json(404, {"ok": False, "error": "result_not_ready"})
            return
        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/command":
            try:
                payload = self._read_json()
                if not payload.get("action"):
                    raise ValueError("action is required")
                command_id = STATE.enqueue(payload)
                self._send_json(202, {"ok": True, "id": command_id, "result_url": f"http://{HOST}:{PORT}/result/{command_id}"})
            except Exception as exc:
                self._send_json(400, {"ok": False, "error": str(exc)})
            return
        if path == "/result":
            try:
                payload = self._read_json()
                command_id = payload.pop("id", None)
                if not command_id:
                    raise ValueError("id is required")
                STATE.set_result(command_id, payload)
                self._send_json(200, {"ok": True})
            except Exception as exc:
                self._send_json(400, {"ok": False, "error": str(exc)})
            return
        self._send_json(404, {"ok": False, "error": "not_found"})

    def log_message(self, fmt, *args):
        print(f"[browser-agent] {fmt % args}", flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"localAI browser agent listening on http://{args.host}:{args.port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == "__main__":
    main()
