import asyncio
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from tests.migration_support import isolated_bot, load_module, source_functions


class Client:
    def __init__(
        self, name, *, max_concurrent_transmissions=100, skip_updates=True, **kwargs
    ):
        self.name = name
        self.transmissions = max_concurrent_transmissions
        self.options = kwargs


class ClientLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        context = isolated_bot()
        self.state = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        sys.modules["bot"].bot_loop = asyncio.get_running_loop()
        sys.modules["pyrogram"].Client = Client
        sys.modules["pyrogram"].enums = SimpleNamespace(
            ParseMode=SimpleNamespace(HTML="html")
        )
        sys.modules["pyrogram.errors"].FloodWait = type("FloodWait", (Exception,), {})
        self.module = load_module("bot.core.tg_client", "bot/core/tg_client.py")
        self.client = self.module.TgClient
        self.pool_stop = AsyncMock()
        self.pool_patch = patch.object(
            self.module.UserSessionPool, "stop_all", self.pool_stop
        )
        self.pool_patch.start()
        self.addCleanup(self.pool_patch.stop)

    async def test_sdk_fallback_has_bounded_default_and_respects_explicit_limit(self):
        self.assertEqual(self.client.wztgClient("test").transmissions, 16)
        self.assertEqual(
            self.client.wztgClient(
                "test", max_concurrent_transmissions=4
            ).transmissions,
            4,
        )

    async def test_restart_batches_include_streams_and_do_not_restart_shared_client_twice(
        self,
    ):
        active = peak = 0
        clients = []

        async def restart():
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0)
            active -= 1

        for i in range(11):
            clients.append(
                SimpleNamespace(name=str(i), restart=AsyncMock(side_effect=restart))
            )
        self.client.bot, self.client.user = clients[:2]
        self.client.helper_bots = dict(enumerate(clients[2:5]))
        self.client.helper_users = dict(enumerate(clients[5:8]))
        self.client.stream_bots = dict(enumerate([*clients[8:], clients[2]]))
        await self.client.reload()
        self.assertLessEqual(peak, 3)
        for client in clients:
            client.restart.assert_awaited_once()
        self.pool_stop.assert_awaited_once()

    async def test_restart_failure_is_reported_after_other_clients_and_pool_cleanup(
        self,
    ):
        failed = SimpleNamespace(
            name="failed", restart=AsyncMock(side_effect=RuntimeError("test failure"))
        )
        others = [SimpleNamespace(name=str(i), restart=AsyncMock()) for i in range(5)]
        self.client.bot = failed
        self.client.stream_bots = dict(enumerate(others))
        with self.assertLogs("migration-tests", level="ERROR"):
            with self.assertRaisesRegex(RuntimeError, "Failed to restart 1"):
                await self.client.reload()
        for client in others:
            client.restart.assert_awaited_once()
        self.pool_stop.assert_awaited_once()

    async def test_cancelled_restart_still_cleans_session_pool(self):
        started = asyncio.Event()

        async def restart():
            started.set()
            await asyncio.Event().wait()

        self.client.bot = SimpleNamespace(name="bot", restart=restart)
        task = asyncio.create_task(self.client.reload())
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.pool_stop.assert_awaited_once()

    async def test_restart_ui_reports_failure_instead_of_leaving_success_message(self):
        edit = AsyncMock()
        handlers = AsyncMock()
        ns = source_functions(
            "bot/__main__.py",
            {"restart_sessions_confirm"},
            {
                "TgClient": SimpleNamespace(
                    reload=AsyncMock(side_effect=RuntimeError("test failure"))
                ),
                "send_message": AsyncMock(return_value="notice"),
                "delete_message": AsyncMock(),
                "edit_message": edit,
                "add_handlers": handlers,
                "LOGGER": Mock(),
            },
        )
        query = SimpleNamespace(
            data="sessionrestart confirm",
            message=SimpleNamespace(reply_to_message="command"),
        )
        await ns["restart_sessions_confirm"](None, query)
        self.assertIn("could not be restarted", edit.await_args.args[1])
        handlers.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
