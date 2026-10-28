import asyncio
import logging
import unittest
from time import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from tests.migration_support import isolated_bot, source_functions


class Message(SimpleNamespace):
    pass


class StatusMigrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        context = isolated_bot()
        self.state = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.state.config.USE_IMAGES = True
        self.state.config.IMAGES = ["test-photo"]
        self.old = Message(
            chat=SimpleNamespace(id=-10001),
            id=10,
            text="old",
            media=True,
            message_thread_id=42,
        )
        self.new = Message(chat=self.old.chat, id=11, text=None, media=False)
        self.send = AsyncMock(return_value=self.new)
        self.edit = AsyncMock(return_value=self.new)
        self.delete = AsyncMock()
        self.read = AsyncMock()
        self.status = {
            -10001: {
                "message": self.old,
                "time": 0,
                "page_no": 1,
                "status": "All",
                "is_user": False,
                "page_step": 1,
            }
        }
        self.ns = source_functions(
            "bot/helper/telegram_helper/message_utils.py",
            {"update_status_message"},
            {
                "Message": Message,
                "Config": self.state.config,
                "intervals": {"stopAll": False, "status": {}},
                "task_dict_lock": asyncio.Lock(),
                "status_dict": self.status,
                "time": time,
                "get_readable_message": self.read,
                "send_message": self.send,
                "edit_message": self.edit,
                "delete_message": self.delete,
                "LOGGER": logging.getLogger("status-tests"),
            },
        )

    async def test_long_status_replaces_photo_once_and_retains_topic(self):
        text = "x" * 1500
        self.read.return_value = (text, [])
        await self.ns["update_status_message"](-10001, force=True)
        self.assertIs(self.status[-10001]["message"], self.new)
        self.assertEqual(self.new.text, text)
        self.assertEqual(self.send.await_args.kwargs["message_thread_id"], 42)
        self.delete.assert_awaited_once_with(self.old)
        await self.ns["update_status_message"](-10001, force=True)
        self.assertEqual(self.send.await_count, 1)
        self.edit.assert_not_awaited()

    async def test_shorter_status_restores_photo_and_tracks_new_message(self):
        self.old.media = False
        self.read.return_value = ("short status", [])
        await self.ns["update_status_message"](-10001, force=True)
        self.assertEqual(self.send.await_args.kwargs["photo"], "IMAGES")
        self.assertIs(self.status[-10001]["message"], self.new)
        self.delete.assert_awaited_once_with(self.old)

    async def test_failed_replacement_keeps_old_status_message(self):
        self.read.return_value = ("x" * 1500, [])
        self.send.return_value = None
        await self.ns["update_status_message"](-10001, force=True)
        self.assertIs(self.status[-10001]["message"], self.old)
        self.delete.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
