"""M0 — the existing send path reaches the mock server and succeeds."""

from __future__ import annotations

import unittest
from unittest import mock

import send_webhook
from tests.mock_discord import MockDiscord

LOCAL_PREFIXES = ("http://127.0.0.1:",)


class SmokeTest(unittest.TestCase):
    def test_send_reaches_mock(self) -> None:
        with MockDiscord() as discord:
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                result = send_webhook.send_message(discord.url, "hello from the smoke test")

            ok = result[0]
            self.assertTrue(ok, msg=f"send failed: {result[1]}")

            posts = discord.of("POST")
            self.assertEqual(len(posts), 1)
            self.assertEqual(posts[0]["body"]["content"], "hello from the smoke test")

    def test_rejects_non_webhook_url(self) -> None:
        ok, detail = send_webhook.send_message("https://example.com/nope", "hi")[:2]
        self.assertFalse(ok)
        self.assertIn("webhook link", detail)

    def test_rejects_empty_message(self) -> None:
        with MockDiscord() as discord:
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                ok, detail = send_webhook.send_message(discord.url, "   ")[:2]
            self.assertFalse(ok)
            self.assertIn("required", detail.lower())
            self.assertEqual(discord.of("POST"), [])


if __name__ == "__main__":
    unittest.main()
