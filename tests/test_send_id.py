"""M1 — send_message requests ?wait=true and surfaces the created message id."""

from __future__ import annotations

import unittest
from unittest import mock

import send_webhook
from tests.mock_discord import MockDiscord

LOCAL_PREFIXES = ("http://127.0.0.1:",)


class SendIdTest(unittest.TestCase):
    def test_post_carries_wait_true(self) -> None:
        with MockDiscord() as discord:
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                send_webhook.send_message(discord.url, "hi")

            posts = discord.of("POST")
            self.assertEqual(len(posts), 1)
            self.assertEqual(posts[0]["query"].get("wait"), ["true"])

    def test_returns_message_id(self) -> None:
        with MockDiscord() as discord:
            discord.next_message_id = "999888777666555444"
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                ok, detail, message_id = send_webhook.send_message(discord.url, "hi")

            self.assertTrue(ok, msg=detail)
            self.assertEqual(message_id, "999888777666555444")

    def test_wait_appends_to_existing_query(self) -> None:
        self.assertEqual(send_webhook._with_wait("https://x/y"), "https://x/y?wait=true")
        self.assertEqual(send_webhook._with_wait("https://x/y?thread_id=1"), "https://x/y?thread_id=1&wait=true")

    def test_failure_returns_no_id(self) -> None:
        with MockDiscord() as discord:
            discord.server.post_status = 404
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                ok, detail, message_id = send_webhook.send_message(discord.url, "hi")

            self.assertFalse(ok)
            self.assertIsNone(message_id)
            self.assertIn("404", detail)


if __name__ == "__main__":
    unittest.main()
