import unittest
from types import MethodType, SimpleNamespace
from unittest.mock import AsyncMock

from tests.migration_support import isolated_bot, message, source_functions


class TaskFeedbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        context = isolated_bot()
        self.state = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.react = AsyncMock()
        ns = source_functions(
            "bot/helper/listeners/task_listener.py",
            {"_task_reaction", "on_download_start"},
            {
                "set_message_reaction": self.react,
                "Config": self.state.config,
            },
            class_name="TaskListener",
        )
        self.listener = SimpleNamespace(
            message=message(),
            bot_pm=False,
            is_super_chat=False,
            is_leech=False,
            is_cancelled=False,
        )
        self.listener._task_reaction = MethodType(ns["_task_reaction"], self.listener)
        self.start = MethodType(ns["on_download_start"], self.listener)

    async def test_engine_acceptance_sends_success_only_once(self):
        await self.start()
        await self.start()
        self.react.assert_awaited_once_with(self.listener.message, "✅")

    async def test_failure_replaces_accepted_reaction_and_late_start_cannot_undo_it(
        self,
    ):
        await self.start()
        await self.listener._task_reaction(False)
        await self.start()
        self.assertEqual(
            [call.args[1] for call in self.react.await_args_list], ["✅", "❌"]
        )

    async def test_rejected_or_cancelled_task_cannot_get_success_reaction(self):
        await self.listener._task_reaction(False)
        await self.start()
        self.react.assert_awaited_once_with(self.listener.message, "❌")
        self.react.reset_mock()
        self.listener.is_cancelled = True
        await self.start()
        self.react.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
