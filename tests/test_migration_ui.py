import ast
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tests.migration_support import (
    ROOT,
    isolated_bot,
    load_module,
    message,
    module,
    source_functions,
)


class Buttons:
    def __init__(self):
        self.items = []

    def data_button(self, text, data, *args, **kwargs):
        self.items.append((text, data))

    def url_button(self, text, url, *args, **kwargs):
        self.items.append((text, url))

    def web_app_button(self, text, url, *args, **kwargs):
        self.items.append((text, url, "webapp"))

    def build_menu(self, *args, **kwargs):
        return self.items


class MigrationUITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        context = isolated_bot()
        self.state = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.style = SimpleNamespace(
            PRIMARY="primary", SUCCESS="success", DANGER="danger"
        )
        ns = {
            "Config": self.state.config,
            "ButtonMaker": Buttons,
            "ButtonStyle": self.style,
            "start": 0,
            "state": "view",
            "referral_settings_text": self.state.referral.referral_settings_text,
        }
        path = ROOT / "bot/modules/bot_settings.py"
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name)
                and t.id
                in {
                    "DEFAULT_DESP",
                    "BOOL_VARS",
                    "LIMIT_VARS",
                    "PROTECTED_VARS",
                    "RESTART_VARS",
                }
                for t in node.targets
            ):
                exec(
                    compile(
                        ast.Module(body=[node], type_ignores=[]), str(path), "exec"
                    ),
                    ns,
                )
        self.settings = source_functions(
            "bot/modules/bot_settings.py", {"get_buttons"}, ns
        )

    async def test_main_menu_keeps_new_modules_and_adds_quota_and_referral(self):
        _, buttons = await self.settings["get_buttons"]()
        callbacks = {button[1] for button in buttons}
        self.assertTrue(
            {"botset quota", "botset referral", "botset setonoff"}.issubset(callbacks)
        )

    async def test_quota_menu_exposes_limit_and_reset_controls(self):
        text, buttons = await self.settings["get_buttons"]("quota")
        callbacks = {button[1] for button in buttons}
        self.assertIn("botset quotaedit USER_QUOTA_DAILY_LIMIT", callbacks)
        self.assertIn("botset quotaedit USER_QUOTA_RESET_HOUR", callbacks)
        self.assertIn("UTC", text)

    async def test_legacy_mode_edits_separate_url_without_overwriting_tunnel(self):
        self.state.config.BASE_URL = "https://test.trycloudflare.com"
        self.state.config.BASE_URL_LEGACY = "http://server:8080"
        self.state.config.BASE_URL_MODE = "legacy"
        text, buttons = await self.settings["get_buttons"]("BASE_URL", "editvar")
        self.assertIn("http://server:8080", text)
        self.assertIn("botset editvar BASE_URL_LEGACY edit", {b[1] for b in buttons})
        self.assertEqual(self.state.config.BASE_URL, "https://test.trycloudflare.com")

    async def test_user_session_reset_and_upstream_limit_navigation_remain(self):
        _, buttons = await self.settings["get_buttons"](
            "USER_SESSION_STRING", "editvar"
        )
        self.assertIn("botset resetvar USER_SESSION_STRING", {b[1] for b in buttons})
        _, buttons = await self.settings["get_buttons"]("TORRENT_LIMIT", "editvar")
        self.assertIn("botset back setlimit", {b[1] for b in buttons})

    async def test_private_http_legacy_link_uses_url_button(self):
        self.state.config.BASE_URL = "https://test.trycloudflare.com"
        self.state.config.BASE_URL_MODE = "legacy"
        self.state.config.BASE_URL_LEGACY = "http://server:8080/"
        ns = source_functions(
            "bot/helper/ext_utils/bot_utils.py",
            {"_selector_base_url", "bt_selection_buttons"},
            {
                "Config": self.state.config,
                "_resolve_bot_id": lambda: "123",
                "derive_pin": lambda *args: "6789",
                "ButtonMaker": Buttons,
                "ButtonStyle": self.style,
                "ChatType": SimpleNamespace(PRIVATE="private"),
            },
        )
        msg = message()
        msg.chat.type = "private"
        buttons = ns["bt_selection_buttons"]("abcd1234", msg)
        self.assertEqual(
            buttons[0], ("Select Files", "http://server:8080/legacy/files?gid=abcd1234")
        )

    async def test_vip_callback_uses_clicking_user_and_original_chat(self):
        self.state.user_data[10] = {
            "VIP_ENABLED": True,
            "VIP_DAILY_LIMIT": 20,
            "VIP_EXPIRE_AT": 0,
        }
        filters = load_module(
            "bot.helper.telegram_helper.filters",
            "bot/helper/telegram_helper/filters.py",
        )
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=10), message=message(uid=1)
        )
        self.assertTrue(await filters.CustomFilters.authorized(None, callback))
        self.state.user_data[10]["VIP_AUTH_REVOKED"] = True
        self.assertFalse(await filters.CustomFilters.authorized(None, callback))

    async def test_subscribe_gate_handles_callback_and_escapes_actor_name(self):
        self.state.auth_chats[-10001] = []
        self.state.config.REFERRAL_SUBSCRIBE_ENABLED = True
        self.state.config.REFERRAL_SUBSCRIBE_CHANNEL_LINK = "https://t.me/test_channel"
        send = AsyncMock(return_value=None)
        dependencies = {
            "bot.helper.telegram_helper.button_build": module(
                "bot.helper.telegram_helper.button_build", ButtonMaker=Buttons
            ),
            "bot.helper.telegram_helper.message_utils": module(
                "bot.helper.telegram_helper.message_utils",
                send_message=send,
                auto_delete_message=AsyncMock(),
            ),
        }
        filters = load_module(
            "bot.helper.telegram_helper.filters",
            "bot/helper/telegram_helper/filters.py",
        )
        original = message(uid=1)
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=10, first_name="<admin>"),
            message=original,
            answer=AsyncMock(),
        )
        client = SimpleNamespace(
            get_chat_member=AsyncMock(
                return_value=SimpleNamespace(status=SimpleNamespace(name="LEFT"))
            )
        )
        with patch.dict("sys.modules", dependencies):
            self.assertFalse(await filters.CustomFilters.authorized(client, callback))
        self.assertIs(send.await_args.args[0], original)
        self.assertIn("&lt;admin&gt;", send.await_args.args[1])
        callback.answer.assert_awaited_once()

    async def test_upstream_data_migration_keeps_custom_quota_vip_and_rewards(self):
        deprecations = load_module(
            "bot.helper.ext_utils.deprecations", "bot/helper/ext_utils/deprecations.py"
        )
        data = {
            "ldump": "b:-100123",
            "USER_QUOTA": {"extra_quota": 15},
            "VIP_ENABLED": True,
            "REFERRAL": {"status": "completed"},
            "SUBSCRIBE_REWARD": {"status": "completed"},
        }
        deprecations.Deprecations.migrate_user(data)
        self.assertEqual(data["LEECH_DUMP_CHATS"], {"Default": "-100123"})
        self.assertEqual(data["USER_QUOTA"]["extra_quota"], 15)
        self.assertTrue(data["VIP_ENABLED"])
        self.assertEqual(data["REFERRAL"]["status"], "completed")
        self.assertEqual(data["SUBSCRIBE_REWARD"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
