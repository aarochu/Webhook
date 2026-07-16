"""M4 — the GUI's send-and-schedule logic, exercised without a display.

Widget wiring (checkbox reads, spinbox bounds, root.after hookup) is verified by
the owner's manual checklist in SPEC M4, not here — this covers the logic those
widgets feed.
"""

from __future__ import annotations

import unittest
from unittest import mock

import send_webhook
from tests.mock_discord import MockDiscord

LOCAL_PREFIXES = ("http://127.0.0.1:",)


class GuiLogicTest(unittest.TestCase):
    def test_checkbox_on_yields_delete_request(self) -> None:
        with MockDiscord() as discord:
            discord.next_message_id = "777"
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                ok, detail, request = send_webhook.send_and_schedule(
                    discord.url, "hi", auto_delete=True, delay=10
                )

            self.assertTrue(ok, msg=detail)
            self.assertIsNotNone(request)
            self.assertEqual(request.message_id, "777")
            self.assertEqual(request.delay, 10)
            self.assertEqual(request.webhook_url, discord.url)

    def test_checkbox_off_yields_nothing_to_schedule(self) -> None:
        with MockDiscord() as discord:
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                _ok, _detail, request = send_webhook.send_and_schedule(
                    discord.url, "hi", auto_delete=False, delay=10
                )

            self.assertIsNone(request)

    def test_spinbox_value_is_clamped(self) -> None:
        """A hand-typed out-of-range spinbox value must not reach root.after."""
        with MockDiscord() as discord:
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                _ok, _detail, high = send_webhook.send_and_schedule(
                    discord.url, "hi", auto_delete=True, delay=99999
                )
                _ok, _detail, low = send_webhook.send_and_schedule(
                    discord.url, "hi", auto_delete=True, delay=-30
                )

            self.assertEqual(high.delay, send_webhook.MAX_DELAY)
            self.assertEqual(low.delay, send_webhook.MIN_DELAY)

    def test_delete_request_drives_the_real_delete(self) -> None:
        """What the GUI hands root.after must actually delete the right message."""
        with MockDiscord() as discord:
            discord.next_message_id = "314159"
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                _ok, _detail, request = send_webhook.send_and_schedule(
                    discord.url, "hi", auto_delete=True, delay=0
                )
                ok, detail = send_webhook.delete_message(request.webhook_url, request.message_id)

            self.assertTrue(ok, msg=detail)
            self.assertTrue(discord.of("DELETE")[0]["path"].endswith("/messages/314159"))


if __name__ == "__main__":
    unittest.main()
