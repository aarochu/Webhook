"""
Mock Discord webhook server for tests.

Stands in for discord.com's webhook endpoints, bound to localhost on an
ephemeral port. Honors ?wait=true (returns a message body with an id) and
records every request so tests can assert on what the app actually sent.

Stdlib only, no outbound network.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

WEBHOOK_ID = "123456789012345678"
WEBHOOK_TOKEN = "mock-token"
DEFAULT_MESSAGE_ID = "111222333444555666"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        """Silence stderr logging during tests."""

    def _record(self, method: str, parsed, body: str | None = None) -> None:
        self.server.requests.append(
            {
                "method": method,
                "path": parsed.path,
                "query": parse_qs(parsed.query),
                "body": json.loads(body) if body else None,
            }
        )

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
        body = self.rfile.read(length).decode("utf-8") if length else None
        self._record("POST", parsed, body)

        if self.server.post_status >= 400:
            self._respond(self.server.post_status, {"message": "mock post failure"})
            return

        # Discord only returns the created message (and its id) when wait=true.
        if parse_qs(parsed.query).get("wait") == ["true"]:
            self._respond(200, {"id": self.server.next_message_id, "content": (body and json.loads(body).get("content"))})
        else:
            self._respond(204)

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
