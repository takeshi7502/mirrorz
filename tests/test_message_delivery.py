import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from tests.migration_support import source_functions


class Message(SimpleNamespace):
    pass


class MessageDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.clock = 0
        self.api = SimpleNamespace(
            send_message=AsyncMock(return_value=Message(id=1)), send_photo=AsyncMock()
        )
        self.ns = {
            "TgClient": SimpleNamespace(bot=self.api),
            "Message": Message,
            "Config": SimpleNamespace(USE_IMAGES=False, IMAGES=[]),
            "LinkPreviewOptions": SimpleNamespace,
            "ReplyParameters": SimpleNamespace,
            "ParseMode": SimpleNamespace(DISABLED="disabled"),
            "LOGGER": Mock(),
            "sleep": AsyncMock(),
            "download_image_url": AsyncMock(),
            "choice": lambda items: items[0],
            "shuffle": lambda items: None,
            "time": lambda: self.clock,
            "_reaction_bad_cache": {},
            "SUCCESS_REACTIONS": ["👍", "👌"],
            "FAIL_REACTIONS": ["👎"],
        }
        for name in [
            "FloodWait",
            "MessageEmpty",
            "EntityBoundsInvalid",
            "MediaCaptionTooLong",
            "PhotoInvalidDimensions",
            "WebpageCurlFailed",
            "WebpageMediaEmpty",
            "MediaEmpty",
            "ReplyMarkupInvalid",
            "MessageTooLong",
            "PeerIdInvalid",
            "ChatWriteForbidden",
        ]:
            self.ns[name] = type(name, (Exception,), {})
        source_functions(
            "bot/helper/telegram_helper/message_utils.py",
            {"send_message", "_get_reaction_candidates", "set_message_reaction"},
            self.ns,
        )

    async def test_chat_id_delivery_preserves_topic(self):
        await self.ns["send_message"](-10001, "status", message_thread_id=42)
        self.assertEqual(
            self.api.send_message.await_args.kwargs["message_thread_id"], 42
        )

    async def test_disabled_photo_fallback_preserves_topic(self):
        await self.ns["send_message"](
            -10001, "status", photo="IMAGES", message_thread_id=42
        )
        self.assertEqual(
            self.api.send_message.await_args.kwargs["message_thread_id"], 42
        )

    async def test_caption_overflow_falls_back_to_full_text_and_same_topic(self):
        self.api.send_photo.side_effect = self.ns["MediaCaptionTooLong"]()
        text = "x" * 2000
        await self.ns["send_message"](-10001, text, photo="photo", message_thread_id=42)
        self.assertEqual(self.api.send_message.await_args.kwargs["text"], text)
        self.assertEqual(
            self.api.send_message.await_args.kwargs["message_thread_id"], 42
        )

    async def test_markup_retry_keeps_topic(self):
        self.api.send_message.side_effect = [
            self.ns["ReplyMarkupInvalid"](),
            Message(id=2),
        ]
        await self.ns["send_message"](
            -10001, "status", ["bad-button"], message_thread_id=42
        )
        self.assertEqual(self.api.send_message.await_count, 2)
        self.assertEqual(
            self.api.send_message.await_args.kwargs["message_thread_id"], 42
        )
        self.assertIsNone(self.api.send_message.await_args.kwargs["reply_markup"])

    async def test_parse_fallback_does_not_loop_or_lose_context(self):
        self.api.send_message.side_effect = self.ns["EntityBoundsInvalid"]()
        result = await self.ns["send_message"](-10001, "bad text", message_thread_id=42)
        self.assertIsInstance(result, str)
        self.assertEqual(self.api.send_message.await_count, 2)
        self.assertEqual(
            self.api.send_message.await_args.kwargs["message_thread_id"], 42
        )

    async def test_invalid_peer_does_not_recurse_indefinitely(self):
        self.api.send_message.side_effect = self.ns["PeerIdInvalid"]("unknown peer")
        result = await self.ns["send_message"](-10001, "status")
        self.assertEqual(result, "unknown peer")
        self.api.send_message.assert_awaited_once()

    async def test_reaction_uses_supported_bound_api(self):
        msg = Message(chat=SimpleNamespace(id=-10001), react=AsyncMock())
        await self.ns["set_message_reaction"](msg, "✅")
        msg.react.assert_awaited_once_with(emoji="👍")

    async def test_transient_reaction_failure_does_not_blacklist_emoji(self):
        msg = Message(
            chat=SimpleNamespace(id=-10001),
            react=AsyncMock(side_effect=[RuntimeError("network"), True]),
        )
        await self.ns["set_message_reaction"](msg, "✅")
        self.assertEqual(self.ns["_reaction_bad_cache"], {})
        await self.ns["set_message_reaction"](msg, "✅")
        self.assertEqual(msg.react.await_count, 2)

    async def test_invalid_reaction_cache_expires_after_chat_rules_change(self):
        msg = Message(
            chat=SimpleNamespace(id=-10001),
            react=AsyncMock(
                side_effect=[RuntimeError("REACTION_INVALID"), True, True, True]
            ),
        )
        await self.ns["set_message_reaction"](msg, "✅")
        await self.ns["set_message_reaction"](msg, "✅")
        self.assertEqual(msg.react.await_args.kwargs["emoji"], "👌")
        self.clock = 601
        await self.ns["set_message_reaction"](msg, "✅")
        self.assertEqual(msg.react.await_args.kwargs["emoji"], "👍")

    async def test_reaction_flood_wait_does_not_sleep_or_retry(self):
        msg = Message(
            chat=SimpleNamespace(id=-10001),
            react=AsyncMock(side_effect=self.ns["FloodWait"]()),
        )
        await self.ns["set_message_reaction"](msg, "✅")
        msg.react.assert_awaited_once()
        self.ns["sleep"].assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
