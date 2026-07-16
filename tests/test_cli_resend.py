"""M2 — CLI auto-resend: a bounded batch reposts the current content; off-path unchanged."""

from __future__ import annotations

import io
import unittest
from unittest import mock

import send_webhook
from tests.mock_discord import MockDiscord

LOCAL_PREFIXES = ("http://127.0.0.1:",)


def startup(
    url: str,
    *,
    auto_delete: str = "n",
    delay: str = "",
    auto_resend: str = "n",
    max_count: str = "",
) -> list:
    """Scripted answers to run_cli's startup prompts, in order."""
    answers = [
        url,   # Webhook URL
        "",    # Display name
        "",    # Profile picture URL
        "",    # User ID to ping
        "1",   # Cooldown seconds
        auto_delete,
    ]
    if auto_delete.lower() in ("y", "yes"):
        answers.append(delay)
    answers.append(auto_resend)
    if auto_resend.lower() in ("y", "yes"):
        answers.append(max_count)
    return answers


class CliResendTest(unittest.TestCase):
    def _run_cli(self, answers: list) -> None:
        with mock.patch("builtins.input", side_effect=answers):
            with mock.patch("sys.stdout", new=io.StringIO()):
                with self.assertRaises(SystemExit):
                    send_webhook.run_cli()

    @staticmethod
    def _wait_for_count(discord: MockDiscord, method: str, n: int, timeout: float = 4.0) -> list:
        """Poll until at least n requests of `method` have arrived (wait_for stops at the first)."""
        import threading as _t

        waited, step, gate = 0.0, 0.02, _t.Event()
        while waited < timeout:
            hits = discord.of(method)
            if len(hits) >= n:
                return hits
            gate.wait(step)
            waited += step
        return discord.of(method)

    def test_bounded_batch_posts_exactly_max_count(self) -> None:
        """Case A: auto-resend on, max-count 3, one message then EOF -> exactly 3 POSTs."""
        with MockDiscord() as discord:
            answers = startup(discord.url, auto_resend="y", max_count="3") + [
                "loop message",  # message line
                "",              # blank line commits the content / starts the batch
                EOFError(),      # end of input — drains the bounded batch, then quits
            ]
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                self._run_cli(answers)

            posts = discord.of("POST")
            self.assertEqual(len(posts), 3, "bounded max-count batch must post exactly N times")
            self.assertTrue(
                all(p["body"]["content"] == "loop message" for p in posts),
                msg="every resent copy must carry the current content",
            )

    def test_bounded_batch_composes_with_auto_delete(self) -> None:
        """Each resent copy schedules its own delete when auto-delete is also on."""
        with MockDiscord() as discord:
            answers = startup(
                discord.url, auto_delete="y", delay="0", auto_resend="y", max_count="2"
            ) + ["gone soon", "", EOFError()]
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                self._run_cli(answers)
                deletes = self._wait_for_count(discord, "DELETE", 2, timeout=4.0)

            self.assertEqual(len(discord.of("POST")), 2)
            self.assertEqual(len(deletes), 2, "auto-delete must fire once per resent copy")

    def test_new_message_swaps_content_and_drains_final_batch(self) -> None:
        """FR-7 swap semantics: a second message replaces the first; on EOF the final
        message's full max-count batch still completes (guards the generation-drain fix)."""
        with MockDiscord() as discord:
            answers = startup(discord.url, auto_resend="y", max_count="2") + [
                "first message", "",   # committed, then immediately superseded
                "second message", "",  # the current message when input ends
                EOFError(),
            ]
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                self._run_cli(answers)

            bodies = [p["body"]["content"] for p in discord.of("POST")]
            # The final generation's batch must fully land (2 of "second message").
            self.assertEqual(
                bodies.count("second message"), 2,
                msg="the last message's bounded batch must not be truncated by the drain",
            )

    def test_resend_off_is_single_send_no_thread(self) -> None:
        """Case B: auto-resend off preserves today's one-POST-per-send path; no resend worker runs."""
        with MockDiscord() as discord:
            answers = startup(discord.url, auto_resend="n") + [
                "just once",
                "",
                EOFError(),
            ]
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                with mock.patch.object(
                    send_webhook, "resend_step", wraps=send_webhook.resend_step
                ) as resend_spy:
                    self._run_cli(answers)

            resend_spy.assert_not_called()  # no background resend thread did any work
            posts = discord.of("POST")
            self.assertEqual(len(posts), 1)
            self.assertEqual(posts[0]["body"]["content"], "just once")


if __name__ == "__main__":
    unittest.main()
