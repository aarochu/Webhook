"""Edit message + sent-history helpers."""

from __future__ import annotations

import unittest
from unittest import mock

import send_webhook
from tests.mock_discord import MockDiscord

LOCAL_PREFIXES = ("http://127.0.0.1:",)


class EditMessageTest(unittest.TestCase):
    def test_edit_hits_messages_endpoint(self) -> None:
        with MockDiscord() as discord:
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                ok, detail = send_webhook.edit_message(discord.url, "555", "updated")

            self.assertTrue(ok, msg=detail)
            patches = discord.of("PATCH")
            self.assertEqual(len(patches), 1)
            self.assertTrue(patches[0]["path"].endswith("/messages/555"))
            self.assertEqual(patches[0]["body"]["content"], "updated")

    def test_empty_content_rejected(self) -> None:
        with MockDiscord() as discord:
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                ok, detail = send_webhook.edit_message(discord.url, "555", "   ")

            self.assertFalse(ok)
            self.assertIn("empty", detail.lower())


class SentHistoryTest(unittest.TestCase):
    def test_remember_and_forget(self) -> None:
        history: list[send_webhook.SentMessage] = []
        send_webhook.remember_sent(history, "99", discord_url := "http://x/w", "hello")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].message_id, "99")
        send_webhook.forget_sent(history, "99")
        self.assertEqual(history, [])

    def test_update_content(self) -> None:
        history: list[send_webhook.SentMessage] = []
        send_webhook.remember_sent(history, "1", "http://x/w", "old")
        send_webhook.update_sent_content(history, "1", "new")
        self.assertEqual(history[0].content, "new")


if __name__ == "__main__":
    unittest.main()
