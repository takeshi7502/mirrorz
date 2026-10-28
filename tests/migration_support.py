import ast
import asyncio
import importlib.util
import logging
import sys
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, **values):
    result = ModuleType(name)
    result.__dict__.update(values)
    return result


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def source_functions(relative, names, namespace, *, class_name=None):
    """Load real function bodies without starting bot clients or service processes."""
    path = ROOT / relative
    tree = ast.parse(path.read_text(encoding="utf-8"))
    body = tree.body
    if class_name:
        body = next(
            node.body
            for node in body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        )
    selected = []
    for node in body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in names
        ):
            node.decorator_list = []
            selected.append(node)
    if len(selected) != len(names):
        raise AssertionError(f"Missing function in {relative}: {names}")
    exec(
        compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"),
        namespace,
    )
    return namespace


class Filter:
    def __init__(self, func):
        self.func = func

    async def __call__(self, client, update):
        return await self.func(self, client, update)


@contextmanager
def isolated_bot():
    """Import the production quota code with in-memory DB and Telegram adapters."""
    state = SimpleNamespace(
        user_data={}, sudo_users=[], auth_chats={}, task_dict={}, saved={}
    )
    bot = module(
        "bot",
        LOGGER=logging.getLogger("migration-tests"),
        user_data=state.user_data,
        sudo_users=state.sudo_users,
        auth_chats=state.auth_chats,
        task_dict=state.task_dict,
        task_dict_lock=asyncio.Lock(),
    )

    async def save(uid):
        await asyncio.sleep(0)
        state.saved[uid] = deepcopy(state.user_data.get(uid, {}))

    dependencies = {
        "bot": bot,
        "wz_bin": module("wz_bin", bin_name=lambda index: f"/test/bin/{index}"),
        "bot.core.tg_client": module(
            "bot.core.tg_client", TgClient=SimpleNamespace(bot=None)
        ),
        "bot.helper.ext_utils.db_handler": module(
            "bot.helper.ext_utils.db_handler",
            database=SimpleNamespace(update_user_data=save),
        ),
        "bot.helper.ext_utils.status_utils": module(
            "bot.helper.ext_utils.status_utils",
            get_readable_time=lambda value: str(int(value)),
        ),
        "bot.helper.telegram_helper.tg_utils": module(
            "bot.helper.telegram_helper.tg_utils", chat_info=AsyncMock()
        ),
        "pyrogram": module("pyrogram"),
        "pyrogram.errors": module(
            "pyrogram.errors",
            UserNotParticipant=type("UserNotParticipant", (Exception,), {}),
        ),
        "pyrogram.filters": module("pyrogram.filters", create=Filter),
        "pyrogram.enums": module(
            "pyrogram.enums", ChatType=SimpleNamespace(PRIVATE="private")
        ),
    }
    for name in (
        "bot",
        "bot.core",
        "bot.helper",
        "bot.helper.ext_utils",
        "bot.helper.telegram_helper",
    ):
        pkg = dependencies.setdefault(name, module(name))
        pkg.__path__ = [str(ROOT / name.replace(".", "/"))]
    with patch.dict(sys.modules, dependencies):
        state.config = load_module(
            "bot.core.config_manager", "bot/core/config_manager.py"
        ).Config
        state.config.OWNER_ID = 1
        state.config.TIMEZONE = "UTC"
        state.config.USER_QUOTA_ENABLED = True
        state.config.USER_QUOTA_DAILY_LIMIT = 2
        state.quota = load_module(
            "bot.helper.ext_utils.user_quota_manager",
            "bot/helper/ext_utils/user_quota_manager.py",
        )
        state.referral = load_module(
            "bot.helper.ext_utils.referral_manager",
            "bot/helper/ext_utils/referral_manager.py",
        )
        yield state


def message(uid=10, mid=100, chat_id=-10001):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=uid, first_name="Test User"),
        sender_chat=None,
        id=mid,
        chat=SimpleNamespace(id=chat_id),
    )


def listener(msg=None, **values):
    msg = msg or message()
    return SimpleNamespace(message=msg, user_id=msg.from_user.id, mid=msg.id, **values)
