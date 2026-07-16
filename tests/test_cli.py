"""M3 — the CLI offers auto-delete and honors the toggle."""

from __future__ import annotations

import io
import unittest
from unittest import mock

import send_webhook
from tests.mock_discord import MockDiscord

LOCAL_PREFIXES = ("http://127.0.0.1:",)


def cli_inputs(url: str, auto_delete: str, delay: str = "") -> list:
    """Scripted answers to run_cli's startup prompts, then one message, then EOF."""
    answers = [
        url,        # Webhook URL
        "",         # Display name
        "",         # Profile picture URL
        "",         # User ID to ping
        "1",        # Cooldown seconds
        auto_delete,
    ]
    if auto_delete.lower() in ("y", "yes"):
        answers.append(delay)
    answers += [
        "hello from the cli",  # message line
        "",                    # blank line sends
        EOFError(),            # quit
    ]
    return answers


class CliAutoDeleteTest(unittest.TestCase):
    def _run_cli(self, answers: list) -> None:
        with mock.patch("builtins.input", side_effect=answers):
            with mock.patch("sys.stdout", new=io.StringIO()):
                with self.assertRaises(SystemExit):
                    send_webhook.run_cli()

    def test_auto_delete_on_posts_then_deletes(self) -> None:
        with MockDiscord() as discord:
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                self._run_cli(cli_inputs(discord.url, "y", "1"))
                deletes = discord.wait_for("DELETE", timeout=3.0)

            posts = discord.of("POST")
            self.assertEqual(len(posts), 1)
            self.assertEqual(posts[0]["body"]["content"], "hello from the cli")
            self.assertEqual(len(deletes), 1)
            self.assertTrue(deletes[0]["path"].endswith("/messages/" + discord.next_message_id))

    def test_auto_delete_off_posts_only(self) -> None:
        with MockDiscord() as discord:
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                self._run_cli(cli_inputs(discord.url, "n"))
                discord.wait_for("DELETE", timeout=1.0)

            self.assertEqual(len(discord.of("POST")), 1)
            self.assertEqual(discord.of("DELETE"), [], "auto-delete was off but a DELETE was sent")

    def test_delay_prompt_skipped_when_toggle_off(self) -> None:
        """With the toggle off, the delay question must not be asked."""
        with MockDiscord() as discord:
            answers = cli_inputs(discord.url, "n")
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                with mock.patch("builtins.input", side_effect=answers) as fake_input:
                    with mock.patch("sys.stdout", new=io.StringIO()):
                        with self.assertRaises(SystemExit):
                            send_webhook.run_cli()

            asked = [c.args[0] for c in fake_input.call_args_list if c.args]
            self.assertFalse(
                any("how many seconds" in q for q in asked),
                msg="delay prompt appeared despite auto-delete being off",
            )


if __name__ == "__main__":
    unittest.main()
