"""M1 — the display-free resend core: count, max-count stop, live content re-read, delete composition."""

from __future__ import annotations

import unittest
from unittest import mock

import send_webhook
from send_webhook import ResendSettings
from tests.mock_discord import MockDiscord

LOCAL_PREFIXES = ("http://127.0.0.1:",)


class ResendCoreTest(unittest.TestCase):
    def test_k_calls_record_k_posts(self) -> None:
        with MockDiscord() as discord:
            settings = ResendSettings(webhook_url=discord.url)
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                for count in range(4):
                    (ok, detail), request, keep_going, _message_id = send_webhook.resend_step(
                        lambda: "tick", settings, count
                    )
                    self.assertTrue(ok, msg=detail)
                    self.assertIsNone(request)
                    self.assertTrue(keep_going, "unlimited resend must never stop on count")

            posts = discord.of("POST")
            self.assertEqual(len(posts), 4)
            self.assertTrue(all(p["body"]["content"] == "tick" for p in posts))

    def test_content_is_reread_each_call(self) -> None:
        """A callback whose return value changes between fires changes the POSTed content."""
        scripted = iter(["first", "second", "third"])
        with MockDiscord() as discord:
            settings = ResendSettings(webhook_url=discord.url)
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                for count in range(3):
                    send_webhook.resend_step(lambda: next(scripted), settings, count)

            bodies = [p["body"]["content"] for p in discord.of("POST")]
            self.assertEqual(bodies, ["first", "second", "third"])

    def test_max_count_stops_at_n(self) -> None:
        with MockDiscord() as discord:
            settings = ResendSettings(webhook_url=discord.url, max_count=3)
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                keeps = []
                for count in range(3):
                    _result, _request, keep_going, _message_id = send_webhook.resend_step(
                        lambda: "tick", settings, count
                    )
                    keeps.append(keep_going)

            # Continue after sends 1 and 2; stop once the 3rd (== N) lands.
            self.assertEqual(keeps, [True, True, False])
            self.assertEqual(len(discord.of("POST")), 3)

    def test_zero_max_count_is_unlimited(self) -> None:
        with MockDiscord() as discord:
            settings = ResendSettings(webhook_url=discord.url, max_count=0)
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                for count in range(6):
                    _result, _request, keep_going, _message_id = send_webhook.resend_step(
                        lambda: "tick", settings, count
                    )
                    self.assertTrue(keep_going)

    def test_failed_send_does_not_consume_the_cap(self) -> None:
        """max-count counts *successful* posts: a failed fire must not advance toward N.

        Sequence fail, ok, fail, ok with max_count=2 — only the two successes count,
        so keep_going stays True through the failures and the first success, and flips
        False only on the second success (2/2)."""
        settings = ResendSettings(webhook_url="http://127.0.0.1:0/x", max_count=2)
        outcomes = iter([
            (False, "HTTP 429: rate limited", None, None),
            (True, "Message sent.", "1", None),
            (False, "HTTP 429: rate limited", None, None),
            (True, "Message sent.", "2", None),
        ])

        def fake_send_and_schedule(*_a, **_k):
            return next(outcomes)

        count = 0
        seen: list[tuple[bool, bool]] = []
        with mock.patch.object(send_webhook, "send_and_schedule", side_effect=fake_send_and_schedule):
            for _ in range(4):
                (ok, _detail), _request, keep_going, _message_id = send_webhook.resend_step(
                    lambda: "tick", settings, count
                )
                if ok:
                    count += 1
                seen.append((ok, keep_going))

        self.assertEqual(seen, [(False, True), (True, True), (False, True), (True, False)])

    def test_auto_delete_composes_each_fire(self) -> None:
        """With auto-delete on, every resent copy returns a DeleteRequest for the mock's id."""
        with MockDiscord() as discord:
            discord.next_message_id = "909"
            settings = ResendSettings(
                webhook_url=discord.url, auto_delete=True, delay=5
            )
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                for count in range(3):
                    _result, request, _keep, _message_id = send_webhook.resend_step(
                        lambda: "tick", settings, count
                    )
                    self.assertIsNotNone(request, "auto-delete on must yield a DeleteRequest each fire")
                    self.assertEqual(request.message_id, "909")
                    self.assertEqual(request.delay, 5)


class ClampMaxCountTest(unittest.TestCase):
    def test_bounds_and_junk(self) -> None:
        self.assertEqual(send_webhook.clamp_max_count(3), 3)
        self.assertEqual(send_webhook.clamp_max_count("3"), 3)
        self.assertEqual(send_webhook.clamp_max_count(0), 0)
        self.assertEqual(send_webhook.clamp_max_count(-4), 0)
        self.assertEqual(send_webhook.clamp_max_count(""), 0)
        self.assertEqual(send_webhook.clamp_max_count("abc"), 0)
        self.assertEqual(send_webhook.clamp_max_count(None), 0)

    def test_decimal_truncates_not_flood(self) -> None:
        """A numeric decimal must stay bounded, not invert into 0 == unlimited."""
        self.assertEqual(send_webhook.clamp_max_count("3.5"), 3)
        self.assertEqual(send_webhook.clamp_max_count("2.9"), 2)
        self.assertEqual(send_webhook.clamp_max_count("-1.5"), 0)


if __name__ == "__main__":
    unittest.main()
