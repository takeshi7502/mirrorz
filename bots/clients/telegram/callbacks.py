import logging
import re
from typing import Callable, Dict

import pyrogram
from pyrogram import Client, filters, types

from bots.clients.telegram.helpers.message_utils import delete_message, edit_message
from bots.clients.telegram.helpers.settings_menu import (
    check_user_input,
    get_user_settings,
)

logger = logging.getLogger("wzml.callbacks")

_callback_handlers: Dict[str, Callable] = {}


def callback_handler(pattern: str):
    def decorator(func: Callable):
        _callback_handlers[pattern] = func
        return func

    return decorator


@callback_handler(r"^status(?P<page>\d+)?$")
async def status_pages(client: Client, callback: types.CallbackQuery):
    try:
        match = re.match(r"^status(\d+)?$", callback.data)
        page = int(match.group(1)) if match and match.group(1) else 1

        from bots.clients.telegram.handlers.status import StatusHandler

        handler = StatusHandler()
        # Default to all tasks for now, unless we encode user_id in callback data later
        msg, reply_markup = await handler.get_status_message(
            user_filter=None, page=page
        )

        if not msg:
            await callback.answer("No active tasks!", show_alert=True)
            await delete_message(callback.message)
            return

        from bots.clients.telegram.helpers.message_utils import (
            edit_message,
        )

        await edit_message(callback.message, msg, reply_markup)
        await callback.answer()
    except Exception as e:
        logger.error(f"Status callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^status_refresh$")
async def status_refresh(client: Client, callback: types.CallbackQuery):
    """Refresh status on current page"""
    try:
        from bots.clients.telegram.handlers.status import StatusHandler

        handler = StatusHandler()
        # Simplified: just request page 1
        msg, reply_markup = await handler.get_status_message(user_filter=None, page=1)

        if not msg:
            await callback.answer("No active tasks!", show_alert=True)
            await delete_message(callback.message)
            return

        from bots.clients.telegram.helpers.message_utils import (
            edit_message,
        )

        await edit_message(callback.message, msg, reply_markup)
        await callback.answer()
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Status refresh error: {e}")
        await callback.answer()


@callback_handler(r"^stats(?P<page>\d+)?$")
async def stats_pages(client: Client, callback: types.CallbackQuery):
    """Handle stats pagination"""
    try:
        await callback.answer()
        await callback.message.edit_text("Statistics\n\n-- implementation pending --")
    except Exception as e:
        logger.error(f"Stats callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^log(?P<page>\d+)?$")
async def log_cb(client: Client, callback: types.CallbackQuery):
    """Handle log pagination"""
    try:
        await callback.answer()
        await callback.message.edit_text("Log Viewer\n\n-- implementation pending --")
    except Exception as e:
        logger.error(f"Log callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^start(?P<action>\w+)?$")
async def start_cb(client: Client, callback: types.CallbackQuery):
    """Handle start menu callbacks"""
    try:
        action = (
            callback.data.replace("start_", "")
            if callback.data.startswith("start_")
            else None
        )

        await callback.answer()
        if action == "mirror":
            await callback.message.edit_text("Use /mirror to start mirroring")
        elif action == "search":
            await callback.message.edit_text("Use /search to search files")
        else:
            await callback.message.edit_text("Welcome to WZML-X!")
    except Exception as e:
        logger.error(f"Start callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^botset(?P<action>\w+)?$")
async def edit_bot_settings(client: Client, callback: types.CallbackQuery):
    """Handle bot settings callbacks"""
    try:
        await callback.answer()
        await callback.message.edit_text("Bot Settings\n\n-- implementation pending --")
    except Exception as e:
        logger.error(f"Bot settings callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^userset\s+(\d+)\s+(\w+)(?:\s+(.+))?$")
async def edit_user_settings(client: Client, callback: types.CallbackQuery):
    """Handle user settings callbacks"""
    try:
        match = re.match(r"^userset\s+(\d+)\s+(\w+)(?:\s+(.+))?$", callback.data)
        if not match:
            await callback.answer("Invalid format!", show_alert=True)
            return

        user_id = int(match.group(1))
        action = match.group(2)
        param = match.group(3) if match.group(3) else None

        if callback.from_user.id != user_id:
            await callback.answer(
                "You cannot edit another user's settings!", show_alert=True
            )
            return

        async def refresh_menu(stype: str = "main"):
            msg_text, buttons = await get_user_settings(callback.from_user, stype)
            await edit_message(callback.message, msg_text, buttons)

        await callback.answer()

        if action == "close":
            await delete_message(callback.message)

        elif action == "toggle" and param:
            from bots.clients.telegram.helpers.user_utils import (
                get_user_data,
                update_user_ldata,
            )

            user_data = await get_user_data(user_id)
            current_value = user_data.get(param, False)
            await update_user_ldata(user_id, param, not current_value)
            await refresh_menu("main")

        elif action in ["set", "file"] and param:
            from bots.clients.telegram.helpers.user_utils import user_settings_text

            if param in user_settings_text:
                prompt_text = user_settings_text[param][2]
                await edit_message(callback.message, f"{prompt_text}")

                async def save_and_refresh():
                    await refresh_menu("main")

                client.loop.create_task(
                    check_user_input(
                        client,
                        user_id,
                        callback.message.chat.id,
                        callback.message,
                        param,
                        save_and_refresh,
                    )
                )
            else:
                await callback.answer("Invalid setting!", show_alert=True)

        else:
            await refresh_menu(action)

    except Exception as e:
        logger.error(f"User settings callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^canall$")
async def cancel_all_update(client: Client, callback: types.CallbackQuery):
    """Handle cancel all confirmation"""
    try:
        from bots.api import api_client

        user_id = callback.from_user.id
        result = await api_client.get_active_tasks(user_id=user_id)
        active_tasks = result.get("data", [])

        if not active_tasks:
            await callback.answer("No active tasks found!", show_alert=True)
            return

        count = 0
        for task in active_tasks:
            try:
                await api_client.cancel_task_v2(task["id"])
                count += 1
            except Exception:
                pass

        await callback.answer(f"Successfully cancelled {count} tasks.", show_alert=True)

        # Refresh status message
        from bots.clients.telegram.handlers.status import StatusHandler

        handler = StatusHandler()
        msg, reply_markup = await handler.get_status_message(user_filter=None, page=1)
        if msg:
            from bots.clients.telegram.helpers.message_utils import (
                delete_message,
                edit_message,
            )

            await edit_message(callback.message, msg, reply_markup)
        else:
            await delete_message(callback.message)

    except Exception as e:
        logger.error(f"Cancel all callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^(?:stopm|cancel)\s*(?P<task_id>\w+)?$")
async def cancel_multi(client: Client, callback: types.CallbackQuery):
    """Handle single or multi-task cancellation via inline button"""
    try:
        match = re.match(r"^(?:stopm|cancel)\s*(\w+)?$", callback.data)
        task_id = match.group(1) if match and match.group(1) else None

        if not task_id:
            await callback.answer("Task ID not provided!", show_alert=True)
            return

        from bots.api import api_client

        try:
            res = await api_client.cancel_task_v2(task_id)
            if "error" not in res:
                await callback.answer(f"Task cancelled: {task_id[:8]}", show_alert=True)
            else:
                await callback.answer(
                    "Task not found or already completed.", show_alert=True
                )
        except Exception as e:
            logger.error(f"Error cancelling task {task_id}: {e}")
            await callback.answer("Failed to cancel task.", show_alert=True)

    except Exception as e:
        logger.error(f"Cancel multi callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^sel(?P<selection>\w+)?$")
async def confirm_selection(client: Client, callback: types.CallbackQuery):
    """Handle file selection confirmation"""
    try:
        await callback.answer()
        await callback.message.edit_text(
            "Selection Confirmed\n\n-- implementation pending --"
        )
    except Exception as e:
        logger.error(f"Selection callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^rss(?P<feed_id>\w+)?$")
async def rss_listener(client: Client, callback: types.CallbackQuery):
    """Handle RSS feed callbacks"""
    try:
        await callback.answer()
        await callback.message.edit_text("RSS Feed\n\n-- implementation pending --")
    except Exception as e:
        logger.error(f"RSS callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^imdb(?P<movie_id>\w+)?$")
async def imdb_callback(client: Client, callback: types.CallbackQuery):
    """Handle IMDB callbacks"""
    try:
        await callback.answer()
        await callback.message.edit_text("IMDB Info\n\n-- implementation pending --")
    except Exception as e:
        logger.error(f"IMDB callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^torser(?P<query>\w+)?$")
async def torrent_search_update(client: Client, callback: types.CallbackQuery):
    """Handle torrent search pagination"""
    try:
        await callback.answer()
        await callback.message.edit_text(
            "Torrent Search\n\n-- implementation pending --"
        )
    except Exception as e:
        logger.error(f"Torrent search callback error: {e}")
        await callback.answer("Error", show_alert=True)


@callback_handler(r"^plugins(?P<action>\w+)?$")
async def edit_plugins_menu(client: Client, callback: types.CallbackQuery):
    """Handle plugin menu callbacks"""
    try:
        await callback.answer()
        await callback.message.edit_text(
            "Plugin Manager\n\n-- implementation pending --"
        )
    except Exception as e:
        logger.error(f"Plugin callback error: {e}")
        await callback.answer("Error", show_alert=True)


async def register_callbacks(client: Client) -> bool:
    """Register all callback query handlers with the client"""
    try:
        for pattern, handler in _callback_handlers.items():
            client.add_handler(
                pyrogram.handlers.CallbackQueryHandler(
                    handler, filters=filters.regex(pattern)
                )
            )
        logger.info(f"Registered {len(_callback_handlers)} callback handlers")
        return True
    except Exception as e:
        logger.error(f"Failed to register callbacks: {e}")
        return False


async def handle_callback(client: Client, callback: types.CallbackQuery):
    """Route callback query to appropriate handler"""
    data = callback.data

    for pattern, handler in _callback_handlers.items():
        if re.match(pattern, data):
            await handler(client, callback)
            return

    await callback.answer("Unknown action", show_alert=True)


__all__ = [
    "register_callbacks",
    "handle_callback",
    "callback_handler",
    "_callback_handlers",
]
