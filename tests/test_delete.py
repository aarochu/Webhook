"""M2 — messages can be deleted by id, and a delete can be scheduled after a delay."""

from __future__ import annotations

import time
import unittest
from unittest import mock

import send_webhook
from tests.mock_discord import MockDiscord

LOCAL_PREFIXES = ("http://127.0.0.1:",)


class DeleteMessageTest(unittest.TestCase):
    def test_delete_hits_messages_endpoint(self) -> None:
        with MockDiscord() as discord:
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                ok, detail = send_webhook.delete_message(discord.url, "555")

            self.assertTrue(ok, msg=detail)
            deletes = discord.of("DELETE")
            self.assertEqual(len(deletes), 1)
            self.assertTrue(deletes[0]["path"].endswith("/messages/555"))

    def test_404_is_reported_not_raised(self) -> None:
        with MockDiscord() as discord:
            discord.delete_status = 404
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                ok, detail = send_webhook.delete_message(discord.url, "555")

            self.assertFalse(ok)
            self.assertIn("404", detail)

    def test_rejects_non_webhook_url(self) -> None:
        ok, detail = send_webhook.delete_message("https://example.com/nope", "555")
        self.assertFalse(ok)
        self.assertIn("webhook link", detail)


class ClampDelayTest(unittest.TestCase):
    def test_bounds_and_junk(self) -> None:
        self.assertEqual(send_webhook.clamp_delay(30), 30)
        self.assertEqual(send_webhook.clamp_delay(-5), 0)
        self.assertEqual(send_webhook.clamp_delay(99999), 3600)
        self.assertEqual(send_webhook.clamp_delay("abc"), 0)
        self.assertEqual(send_webhook.clamp_delay(None), 0)


class SendAndScheduleTest(unittest.TestCase):
    def test_returns_request_when_auto_delete_on(self) -> None:
        with MockDiscord() as discord:
            discord.next_message_id = "42"
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                ok, detail, _message_id, request = send_webhook.send_and_schedule(
                    discord.url, "hi", auto_delete=True, delay=7
                )

            self.assertTrue(ok, msg=detail)
            self.assertIsNotNone(request)
            self.assertEqual(request.message_id, "42")
            self.assertEqual(request.delay, 7)

    def test_no_request_when_auto_delete_off(self) -> None:
        with MockDiscord() as discord:
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                ok, detail, _message_id, request = send_webhook.send_and_schedule(
                    discord.url, "hi", auto_delete=False
                )

            self.assertTrue(ok, msg=detail)
            self.assertIsNone(request)

    def test_no_request_when_send_fails(self) -> None:
        with MockDiscord() as discord:
            discord.server.post_status = 500
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                ok, _detail, _message_id, request = send_webhook.send_and_schedule(
                    discord.url, "hi", auto_delete=True
                )

            self.assertFalse(ok)
            self.assertIsNone(request)
            self.assertEqual(discord.of("DELETE"), [])


class ScheduledDeleteTest(unittest.TestCase):
    def test_delete_fires_after_delay(self) -> None:
        with MockDiscord() as discord:
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                _ok, _detail, _message_id, request = send_webhook.send_and_schedule(
                    discord.url, "self destructing", auto_delete=True, delay=1
                )
                self.assertIsNotNone(request)

                self.assertEqual(discord.of("DELETE"), [], "delete fired before its delay elapsed")

                send_webhook.arm_delete_timer(request)
                deletes = discord.wait_for("DELETE", timeout=2.0)

            self.assertEqual(len(deletes), 1)
            self.assertTrue(deletes[0]["path"].endswith(f"/messages/{request.message_id}"))

    def test_zero_delay_fires_promptly(self) -> None:
        with MockDiscord() as discord:
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                _ok, _detail, _message_id, request = send_webhook.send_and_schedule(
                    discord.url, "gone instantly", auto_delete=True, delay=0
                )
                started = time.monotonic()
                send_webhook.arm_delete_timer(request)
                deletes = discord.wait_for("DELETE", timeout=2.0)

            self.assertEqual(len(deletes), 1)
            self.assertLess(time.monotonic() - started, 1.0)

    def test_failed_delete_reports_to_callback(self) -> None:
        with MockDiscord() as discord:
            discord.delete_status = 404
            seen: list[tuple[bool, str]] = []
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                _ok, _detail, _message_id, request = send_webhook.send_and_schedule(
                    discord.url, "hi", auto_delete=True, delay=0
                )
                send_webhook.arm_delete_timer(request, on_done=lambda ok, d: seen.append((ok, d)))
                discord.wait_for("DELETE", timeout=2.0)
                time.sleep(0.1)

            self.assertEqual(len(seen), 1)
            self.assertFalse(seen[0][0])
            self.assertIn("404", seen[0][1])


if __name__ == "__main__":
    unittest.main()
