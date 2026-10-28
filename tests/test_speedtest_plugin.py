import asyncio
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from tests.migration_support import source_functions


class SpeedtestPluginTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.addCleanup(self.pool.shutdown, wait=True)
        ns = source_functions(
            "bot/helper/ext_utils/bot_utils.py",
            {"sync_to_async"},
            {
                "partial": partial,
                "THREAD_POOL": self.pool,
                "bot_loop": asyncio.get_running_loop(),
            },
        )
        self.share_thread = None
        self.share_error = False
        self.data = {"share": "https://image.example/result.png"}

        def share():
            self.share_thread = threading.get_ident()
            if self.share_error:
                raise RuntimeError("share service unavailable")

        result = SimpleNamespace(share=share, dict=lambda: self.data)
        speedtest = SimpleNamespace(
            results=result, get_best_server=Mock(), download=Mock(), upload=Mock()
        )
        self.status = SimpleNamespace(id=1)
        self.sent = SimpleNamespace(id=2)
        self.send = AsyncMock(side_effect=[self.status, self.sent])
        self.delete = AsyncMock()
        self.edit = AsyncMock()
        plugin = source_functions(
            "plugins/speedtest/speedtest.py",
            {"speedtest_command"},
            {
                "sync_to_async": ns["sync_to_async"],
                "Speedtest": lambda: speedtest,
                "ConfigRetrievalError": type("ConfigRetrievalError", (Exception,), {}),
                "send_message": self.send,
                "delete_message": self.delete,
                "edit_message": self.edit,
                "format_result": lambda data: "formatted result",
                "LOGGER": Mock(),
            },
        )
        self.command = plugin["speedtest_command"]

    async def test_share_creation_runs_off_event_loop(self):
        await self.command(None, "command")
        self.assertNotEqual(self.share_thread, threading.get_ident())
        self.delete.assert_awaited_once_with(self.status)

    async def test_failed_result_delivery_edits_status_instead_of_deleting_it(self):
        for failure in (None, "photo delivery failed"):
            self.send.side_effect = [self.status, failure]
            await self.command(None, "command")
        self.delete.assert_not_awaited()
        self.assertEqual(self.edit.await_count, 2)
        self.edit.assert_awaited_with(self.status, "formatted result")

    async def test_share_service_failure_still_delivers_result_without_photo(self):
        self.share_error = True
        self.data["share"] = None
        await self.command(None, "command")
        self.assertIsNone(self.send.await_args.kwargs["photo"])
        self.delete.assert_awaited_once_with(self.status)


if __name__ == "__main__":
    unittest.main()
