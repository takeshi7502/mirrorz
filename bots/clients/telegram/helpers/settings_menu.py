import logging
import asyncio
from typing import Optional

from pyrogram import Client, types
from pyrogram.handlers import MessageHandler
from pyrogram.filters import create

from bots.clients.telegram.helpers.button_utils import ButtonMaker
from bots.clients.telegram.helpers.message_utils import edit_message
from bots.clients.telegram.helpers.user_utils import (
    get_user_data,
    user_settings_text,
    update_user_ldata,
)

logger = logging.getLogger("wzml.telegram.settings_callback")

# Cache to stop the previous listener if a new one is launched
_listener_tasks = {}


async def get_user_settings(from_user: types.User, stype: str = "main"):
    user_id = from_user.id
    user_data = await get_user_data(user_id)

    user_name = from_user.first_name
    if from_user.last_name:
        user_name += f" {from_user.last_name}"

    msg_text = f"<b><u>User Settings for {from_user.mention}</u></b>\n\n"

    buttons = ButtonMaker()

    if stype == "main":
        buttons.data_button("General Settings", f"userset {user_id} general")
        buttons.data_button("Mirror Settings", f"userset {user_id} mirror")
        buttons.data_button("Leech Settings", f"userset {user_id} leech")
        buttons.data_button("Uphoster Settings", f"userset {user_id} uphoster")
        buttons.data_button("FF Media Settings", f"userset {user_id} ffset")
        buttons.data_button("Advanced Settings", f"userset {user_id} advanced")
        buttons.data_button("Close", f"userset {user_id} close", position="footer")

    elif stype == "general":
        msg_text += "<b>General Settings</b>\nConfigure your global preferences here."
        rclone_mode = user_data.get("RCLONE_MODE", False)
        gdrive_mode = user_data.get("GDRIVE_MODE", False)

        buttons.data_button(
            f"RClone Mode: {'ON' if rclone_mode else 'OFF'}",
            f"userset {user_id} toggle RCLONE_MODE",
        )
        buttons.data_button(
            f"GDrive Mode: {'ON' if gdrive_mode else 'OFF'}",
            f"userset {user_id} toggle GDRIVE_MODE",
        )

        buttons.data_button("Back", f"userset {user_id} main", position="footer")
        buttons.data_button("Close", f"userset {user_id} close", position="footer")

    elif stype == "leech":
        msg_text += "<b>Leech Settings</b>\nConfigure your upload preferences here."

        buttons.data_button("Thumbnail", f"userset {user_id} file THUMBNAIL")
        buttons.data_button(
            "Leech Split Size", f"userset {user_id} set LEECH_SPLIT_SIZE"
        )
        buttons.data_button(
            "Leech Destination", f"userset {user_id} set LEECH_DUMP_CHAT"
        )
        buttons.data_button("Leech Prefix", f"userset {user_id} set LEECH_PREFIX")
        buttons.data_button("Leech Suffix", f"userset {user_id} set LEECH_SUFFIX")
        buttons.data_button("Leech Caption", f"userset {user_id} set LEECH_CAPTION")
        buttons.data_button(
            "Thumbnail Layout", f"userset {user_id} set THUMBNAIL_LAYOUT"
        )

        as_doc = user_data.get("AS_DOCUMENT", False)
        buttons.data_button(
            f"Send As: {'Document' if as_doc else 'Media'}",
            f"userset {user_id} toggle AS_DOCUMENT",
        )

        buttons.data_button("Back", f"userset {user_id} main", position="footer")
        buttons.data_button("Close", f"userset {user_id} close", position="footer")

    elif stype == "mirror":
        msg_text += "<b>Mirror Settings</b>\nConfigure RClone and GDrive."
        buttons.data_button("RClone Tools", f"userset {user_id} rclone")
        buttons.data_button("GDrive Tools", f"userset {user_id} gdrive")
        buttons.data_button("Back", f"userset {user_id} main", position="footer")
        buttons.data_button("Close", f"userset {user_id} close", position="footer")

    elif stype == "uphoster":
        msg_text += "<b>Uphoster Settings</b>\nConfigure file hosts."
        buttons.data_button("Gofile Token", f"userset {user_id} set GOFILE_TOKEN")
        buttons.data_button(
            "Buzzheavier Token", f"userset {user_id} set BUZZHEAVIER_TOKEN"
        )
        buttons.data_button("PixelDrain Key", f"userset {user_id} set PIXELDRAIN_KEY")
        buttons.data_button("Back", f"userset {user_id} main", position="footer")
        buttons.data_button("Close", f"userset {user_id} close", position="footer")

    elif stype == "rclone":
        msg_text += "<b>RClone Settings</b>"
        buttons.data_button("RClone Config", f"userset {user_id} file RCLONE_CONFIG")
        buttons.data_button("RClone Path", f"userset {user_id} set RCLONE_PATH")
        buttons.data_button("RClone Flags", f"userset {user_id} set RCLONE_FLAGS")
        buttons.data_button("Back", f"userset {user_id} mirror", position="footer")

    elif stype == "gdrive":
        msg_text += "<b>GDrive Settings</b>"
        buttons.data_button("Token Pickle", f"userset {user_id} file TOKEN_PICKLE")
        buttons.data_button("GDrive ID", f"userset {user_id} set GDRIVE_ID")
        buttons.data_button("Index URL", f"userset {user_id} set INDEX_URL")
        buttons.data_button("Back", f"userset {user_id} mirror", position="footer")

    elif stype in ["ffset", "advanced"]:
        msg_text += f"<b>{stype.title()} Settings</b>\n"
        buttons.data_button("Back", f"userset {user_id} main", position="footer")
        buttons.data_button("Close", f"userset {user_id} close", position="footer")

    return msg_text, buttons.build_menu(2)


async def check_user_input(
    client: Client,
    user_id: int,
    chat_id: int,
    message: types.Message,
    setting_type: str,
    rfunc,
) -> None:
    """Non-blocking event listener for user settings input."""
    # Cancel previous listener if exists
    if user_id in _listener_tasks:
        _listener_tasks[user_id].cancel()

    future = asyncio.Future()

    async def filter_func(_, __, m: types.Message):
        return (
            m.from_user.id == user_id
            and m.chat.id == chat_id
            and (m.text or m.photo or m.document)
        )

    handler = MessageHandler(
        lambda c, m: future.set_result(m) if not future.done() else None,
        filters=create(filter_func),
    )

    client.add_handler(handler, group=-1)

    try:
        # Await the response
        response_msg: types.Message = await asyncio.wait_for(future, timeout=60)

        # Save setting based on type
        if setting_type == "THUMBNAIL":
            if response_msg.photo:
                await update_user_ldata(
                    user_id, setting_type, response_msg.photo.file_id
                )
        elif setting_type in ["RCLONE_CONFIG", "TOKEN_PICKLE"]:
            if response_msg.document:
                await update_user_ldata(
                    user_id, setting_type, response_msg.document.file_id
                )
        else:
            if response_msg.text:
                await update_user_ldata(user_id, setting_type, response_msg.text)

        # Send confirmation and return to menu
        await rfunc()

    except asyncio.TimeoutError:
        logger.warning(f"Timeout waiting for input from user {user_id}")
    finally:
        client.remove_handler(*handler)
        if user_id in _listener_tasks:
            del _listener_tasks[user_id]
