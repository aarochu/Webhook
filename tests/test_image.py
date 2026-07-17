"""Image attachment upload for webhook messages."""

from __future__ import annotations

import unittest
from unittest import mock

import send_webhook
from send_webhook import ImageAttachment
from tests.mock_discord import MockDiscord

LOCAL_PREFIXES = ("http://127.0.0.1:",)
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class AttachmentValidationTest(unittest.TestCase):
    def test_rejects_unknown_extension(self) -> None:
        attachment, err = send_webhook.attachment_from_bytes("file.txt", b"hello")
        self.assertIsNone(attachment)
        self.assertIsNotNone(err)

    def test_accepts_png_bytes(self) -> None:
        attachment, err = send_webhook.attachment_from_bytes("shot.png", PNG_BYTES)
        self.assertIsNone(err)
        self.assertEqual(attachment.filename, "shot.png")
        self.assertEqual(attachment.content_type, "image/png")


class SendImageTest(unittest.TestCase):
    def test_send_image_only_uses_multipart(self) -> None:
        attachment = ImageAttachment("shot.png", PNG_BYTES, "image/png")
        with MockDiscord() as discord:
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                ok, detail, message_id = send_webhook.send_message(
                    discord.url, "", attachment=attachment
                )

            self.assertTrue(ok, msg=detail)
            self.assertEqual(message_id, discord.next_message_id)
            posts = discord.of("POST")
            self.assertEqual(len(posts), 1)
            self.assertTrue(posts[0].get("multipart"))
            self.assertEqual(posts[0]["filename"], "shot.png")

    def test_text_or_image_required(self) -> None:
        with MockDiscord() as discord:
            with mock.patch.object(send_webhook, "WEBHOOK_PREFIXES", LOCAL_PREFIXES):
                ok, detail, message_id = send_webhook.send_message(discord.url, "   ")
            self.assertFalse(ok)
            self.assertIn("required", detail.lower())
            self.assertIsNone(message_id)


if __name__ == "__main__":
    unittest.main()
