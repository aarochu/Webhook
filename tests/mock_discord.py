"""
Mock Discord webhook server for tests.

Stands in for discord.com's webhook endpoints, bound to localhost on an
ephemeral port. Honors ?wait=true (returns a message body with an id) and
records every request so tests can assert on what the app actually sent.

Stdlib only, no outbound network.
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

WEBHOOK_ID = "123456789012345678"
WEBHOOK_TOKEN = "mock-token"
DEFAULT_MESSAGE_ID = "111222333444555666"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        """Silence stderr logging during tests."""

    def _record(self, method: str, parsed, body: str | bytes | None = None, *, multipart: bool = False) -> None:
        entry: dict = {
            "method": method,
            "path": parsed.path,
            "query": parse_qs(parsed.query),
        }
        if multipart and isinstance(body, dict):
            entry["multipart"] = True
            entry["payload"] = body.get("payload")
            entry["filename"] = body.get("filename")
        else:
            entry["body"] = json.loads(body) if body else None
        self.server.requests.append(entry)

    def _parse_multipart(self, body: bytes, content_type: str) -> dict:
        match = re.search(r"boundary=(.+)", content_type)
        if not match:
            return {}
        boundary = match.group(1).strip().strip('"')
        parts = body.split(f"--{boundary}".encode())
        payload = None
        filename = None
        for part in parts:
            if b"name=\"payload_json\"" in part:
                chunks = part.split(b"\r\n\r\n", 1)
                if len(chunks) == 2:
                    payload = json.loads(chunks[1].rstrip(b"\r\n"))
            if b"filename=" in part:
                header = part.split(b"\r\n\r\n", 1)[0].decode("utf-8", errors="replace")
                name_match = re.search(r'filename="([^"]+)"', header)
                if name_match:
                    filename = name_match.group(1)
        return {"payload": payload, "filename": filename}

    def _respond(self, status: int, payload: dict | None = None) -> None:
        data = json.dumps(payload).encode("utf-8") if payload is not None else b""
        self.send_response(status)
        if data:
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        content_type = self.headers.get("Content-Type", "")

        if content_type.startswith("multipart/form-data"):
            parsed_body = self._parse_multipart(raw, content_type)
            self._record("POST", parsed, parsed_body, multipart=True)
            content = (parsed_body.get("payload") or {}).get("content")
        else:
            body = raw.decode("utf-8") if raw else None
            self._record("POST", parsed, body)
            content = body and json.loads(body).get("content")

        if self.server.post_status >= 400:
            self._respond(self.server.post_status, {"message": "mock post failure"})
            return

        # Discord only returns the created message (and its id) when wait=true.
        if parse_qs(parsed.query).get("wait") == ["true"]:
            self._respond(200, {"id": self.server.next_message_id, "content": content})
        else:
            self._respond(204)

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else None
        self._record("PATCH", parsed, body)

        if self.server.patch_status >= 400:
            self._respond(self.server.patch_status, {"message": "mock patch failure"})
            return
        content = body and json.loads(body).get("content")
        self._respond(200, {"id": parsed.path.rsplit("/", 1)[-1], "content": content})

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        self._record("DELETE", parsed)

        if self.server.delete_status >= 400:
            self._respond(self.server.delete_status, {"message": "Unknown Message", "code": 10008})
            return
        self._respond(self.server.delete_status)


class MockDiscord:
    """Context-managed mock. Use `.url` as the webhook URL under test."""

    def __init__(self) -> None:
        self.server = HTTPServer(("127.0.0.1", 0), _Handler)
        self.server.requests = []
        self.server.next_message_id = DEFAULT_MESSAGE_ID
        self.server.post_status = 200
        self.server.delete_status = 204
        self.server.patch_status = 200
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "MockDiscord":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()
        self._thread.join(timeout=5)

    @property
    def url(self) -> str:
        port = self.server.server_port
        return f"http://127.0.0.1:{port}/api/webhooks/{WEBHOOK_ID}/{WEBHOOK_TOKEN}"

    @property
    def next_message_id(self) -> str:
        return self.server.next_message_id

    @next_message_id.setter
    def next_message_id(self, value: str) -> None:
        self.server.next_message_id = value

    @property
    def delete_status(self) -> int:
        return self.server.delete_status

    @delete_status.setter
    def delete_status(self, value: int) -> None:
        self.server.delete_status = value

    @property
    def requests(self) -> list[dict]:
        return list(self.server.requests)

    def of(self, method: str) -> list[dict]:
        return [r for r in self.server.requests if r["method"] == method]

    def wait_for(self, method: str, timeout: float = 2.0) -> list[dict]:
        """Block until at least one request of `method` arrives, or timeout."""
        deadline = threading.Event()
        step = 0.02
        waited = 0.0
        while waited < timeout:
            hits = self.of(method)
            if hits:
                return hits
            deadline.wait(step)
            waited += step
        return self.of(method)
