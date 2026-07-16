"""M3 — the GUI's auto-resend decision logic, exercised without a display.

Widget wiring (checkbox swaps the button, root.after scheduling, live message-box
re-read) is verified by the owner's manual GUI checklist in SPEC M3, not here —
this covers the display-free helpers those widgets feed.
"""

from __future__ import annotations

import unittest
from unittest import mock

import send_webhook
from send_webhook import ResendSettings
from tests.mock_discord import MockDiscord

LOCAL_PREFIXES = ("http://127.0.0.1:",)


class GuiAfterFireTest(unittest.TestCase):
    def test_continue_when_keep_going(self) -> None:
        active, decision = send_webhook.gui_after_fire(keep_going=True)
        self.assertTrue(active)
        self.assertEqual(decision, "continue")

    def test_stop_when_not_keep_going(self) -> None:
        active, decision = send_webhook.gui_after_fire(keep_going=False)
        self.assertFalse(active, "reaching max-count must leave the loop inactive")
        self.assertEqual(decision, "stop")

    def test_max_count_drives_stop_end_to_end(self) -> None:
        """Through the real core: the fire that hits max-count reports 'stop' (toggle flips Off)."""
        with MockDiscord() as discord:
            settings = ResendSettings(webhook_url=discord.url, max_count=2)
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                decisions = []
                for count in range(2):
                    _result, _request, keep_going = send_webhook.resend_step(
                        lambda: "tick", settings, count
                    )
                    decisions.append(send_webhook.gui_after_fire(keep_going)[1])

            self.assertEqual(decisions, ["continue", "stop"])


class ResendButtonLabelTest(unittest.TestCase):
    def test_checkbox_off_is_plain_send(self) -> None:
        self.assertEqual(send_webhook.resend_button_label(False, False), "Send message")
        self.assertEqual(send_webhook.resend_button_label(False, True), "Send message")

    def test_checkbox_on_reflects_loop_state(self) -> None:
        self.assertIn("OFF", send_webhook.resend_button_label(True, False))
        self.assertIn("ON", send_webhook.resend_button_label(True, True))


class BuildGuiContentTest(unittest.TestCase):
    def test_no_ping_returns_trimmed_content(self) -> None:
        content, err = send_webhook.build_gui_content("  hi there \n", ping_user=False, user_id="")
        self.assertIsNone(err)
        self.assertEqual(content, "hi there")

    def test_ping_prepends_mention(self) -> None:
        content, err = send_webhook.build_gui_content("hi", ping_user=True, user_id="42")
        self.assertIsNone(err)
        self.assertEqual(content, "<@42> hi")

    def test_ping_not_duplicated_if_already_present(self) -> None:
        content, _err = send_webhook.build_gui_content("<@42> hi", ping_user=True, user_id="42")
        self.assertEqual(content, "<@42> hi")

    def test_ping_requires_numeric_id(self) -> None:
        content, err = send_webhook.build_gui_content("hi", ping_user=True, user_id="not-a-number")
        self.assertIsNone(content)
        self.assertIsNotNone(err)


if __name__ == "__main__":
    unittest.main()
