import asyncio
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from tests.migration_support import isolated_bot, source_functions


class TunnelSyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        context = isolated_bot()
        self.state = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.state.config.BASE_URL_LEGACY = "http://legacy:8080"
        self.db = SimpleNamespace(_return=False, update_config=AsyncMock())
        self.ns = source_functions(
            "bot/helper/ext_utils/tunnel_monitor.py",
            {
                "_apply_tunnel_url",
                "apply_tunnel_url_once",
                "_tunnel_monitor_loop",
                "start_tunnel_monitor",
            },
            {
                "Config": self.state.config,
                "database": self.db,
                "_last_persisted_url": None,
                "_update_lock": asyncio.Lock(),
                "_monitor_task": None,
                "LOGGER": logging.getLogger("tunnel-tests"),
                "bot_loop": asyncio.get_running_loop(),
                "_read_tunnel_url": AsyncMock(return_value=None),
                "sleep": asyncio.sleep,
            },
        )

    async def test_changed_url_updates_runtime_and_db_but_not_legacy(self):
        self.assertTrue(
            await self.ns["_apply_tunnel_url"](" https://new.trycloudflare.com/ ")
        )
        self.assertEqual(self.state.config.BASE_URL, "https://new.trycloudflare.com")
        self.assertEqual(self.state.config.BASE_URL_LEGACY, "http://legacy:8080")
        self.db.update_config.assert_awaited_once_with(
            {"BASE_URL": "https://new.trycloudflare.com"}
        )

    async def test_concurrent_unchanged_polls_do_not_keep_writing(self):
        await asyncio.gather(
            *(self.ns["_apply_tunnel_url"]("https://new.example") for _ in range(10))
        )
        self.assertEqual(self.db.update_config.await_count, 1)

    async def test_db_failure_does_not_block_url_and_is_retried(self):
        self.db.update_config.side_effect = [RuntimeError("offline"), None]
        with self.assertLogs("tunnel-tests", level="WARNING"):
            await self.ns["_apply_tunnel_url"]("https://new.example")
        self.assertEqual(self.state.config.BASE_URL, "https://new.example")
        self.assertIsNone(self.ns["_last_persisted_url"])
        await self.ns["_apply_tunnel_url"]("https://new.example")
        self.assertEqual(self.db.update_config.await_count, 2)
        self.assertEqual(self.ns["_last_persisted_url"], "https://new.example")

    async def test_url_is_persisted_after_db_connects_even_if_runtime_unchanged(self):
        self.db._return = True
        await self.ns["_apply_tunnel_url"]("https://new.example")
        self.db.update_config.assert_not_awaited()
        self.db._return = False
        await self.ns["_apply_tunnel_url"]("https://new.example")
        self.db.update_config.assert_awaited_once()

    async def test_empty_url_does_not_clear_active_url(self):
        self.state.config.BASE_URL = "https://active.example"
        self.assertFalse(await self.ns["_apply_tunnel_url"](None))
        self.assertEqual(self.state.config.BASE_URL, "https://active.example")
        self.db.update_config.assert_not_awaited()

    async def test_initial_read_uses_same_sync_path(self):
        self.ns["_read_tunnel_url"].return_value = "https://initial.example"
        await self.ns["apply_tunnel_url_once"]()
        self.assertEqual(self.state.config.BASE_URL, "https://initial.example")
        self.db.update_config.assert_awaited_once()

    async def test_monitor_start_is_idempotent(self):
        first = self.ns["start_tunnel_monitor"]()
        self.assertIs(self.ns["start_tunnel_monitor"](), first)
        await asyncio.sleep(0)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first


if __name__ == "__main__":
    unittest.main()
