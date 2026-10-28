import re
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from tests.migration_support import isolated_bot, message, source_functions


class TransferPreparationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        context = isolated_bot()
        self.state = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.react = AsyncMock()
        self.link = "https://source.example/file"
        self.debrid = False
        self.error = type("DirectDownloadLinkException", (Exception,), {})

        def parse(tokens, options):
            options["link"] = self.link
            options["-ad"] = self.debrid

        async def run_sync(func, *args):
            return func(*args)

        self.engine = AsyncMock()
        self.resolve = Mock(return_value="https://resolved.example/file")
        self.debrid_resolve = AsyncMock()
        self.ns = source_functions(
            "bot/modules/mirror_leech.py",
            {"new_event"},
            {
                "Config": self.state.config,
                "DOWNLOAD_DIR": "/downloads/",
                "Mirror": object,
                "LOGGER": Mock(),
                "pre_task_check": AsyncMock(return_value=(None, None)),
                "set_message_reaction": self.react,
                "send_message": AsyncMock(),
                "delete_links": AsyncMock(),
                "quota_reserve_task": AsyncMock(),
                "arg_parser": parse,
                "is_telegram_link": lambda link: False,
                "is_url": lambda link: link.startswith("https://"),
                "is_magnet": lambda link: link.startswith("magnet:"),
                "is_rclone_path": lambda link: False,
                "is_gdrive_id": lambda link: False,
                "is_gdrive_link": lambda link: False,
                "is_mega_link": lambda link: False,
                "aiopath": SimpleNamespace(exists=AsyncMock(return_value=False)),
                "get_content_type": AsyncMock(return_value="text/html"),
                "re_match": re.match,
                "sync_to_async": run_sync,
                "direct_link_generator": self.resolve,
                "DirectDownloadLinkException": self.error,
                "alldebrid_resolve_magnet": self.debrid_resolve,
                "add_aria2_download": self.engine,
                "COMMAND_USAGE": {"mirror": ("usage", None)},
            },
            class_name="Mirror",
        )
        msg = message()
        msg.text = "/mirror source"
        msg.reply_to_message = None
        self.listener = SimpleNamespace(
            message=msg,
            is_leech=False,
            is_uphoster=False,
            is_qbit=False,
            is_jd=False,
            is_nzb=False,
            is_seedr=False,
            is_cancelled=False,
            bulk=[],
            same_dir={},
            mid=msg.id,
            user_id=10,
            default_metadata_dict={},
            audio_metadata_dict={},
            video_metadata_dict={},
            subtitle_metadata_dict={},
            run_multi=AsyncMock(),
            get_tag=AsyncMock(),
            before_start=AsyncMock(),
            _set_mode_engine=Mock(),
            remove_from_same_dir=AsyncMock(),
        )

    async def test_direct_link_failure_gets_failure_without_premature_success(self):
        def fail(link):
            self.react.assert_not_awaited()
            raise self.error("ERROR: direct link unavailable")

        self.resolve.side_effect = fail
        await self.ns["new_event"](self.listener)
        self.react.assert_awaited_once_with(self.listener.message, "❌")
        self.engine.assert_not_awaited()

    async def test_alldebrid_failure_does_not_get_success_reaction(self):
        self.link = "magnet:?xt=urn:btih:test"
        self.debrid = True
        self.debrid_resolve.side_effect = self.error("ERROR: debrid unavailable")
        await self.ns["new_event"](self.listener)
        self.react.assert_awaited_once_with(self.listener.message, "❌")
        self.engine.assert_not_awaited()

    async def test_successful_preparation_does_not_claim_success_before_engine_accepts(
        self,
    ):
        async def engine(listener, *args):
            self.resolve.assert_called_once()
            self.react.assert_not_awaited()

        self.engine.side_effect = engine
        await self.ns["new_event"](self.listener)
        self.engine.assert_awaited_once()
        self.react.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
