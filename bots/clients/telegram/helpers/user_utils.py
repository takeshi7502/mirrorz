import logging
import time
from typing import Dict, Any, Optional

from db.mongodb import get_mongodb_client

logger = logging.getLogger("wzml.telegram.user_utils")

# Cache to avoid hammering the DB for every single status update or check
USER_DATA: Dict[int, Dict[str, Any]] = {}

leech_options = [
    "THUMBNAIL",
    "LEECH_SPLIT_SIZE",
    "LEECH_DUMP_CHAT",
    "LEECH_PREFIX",
    "LEECH_SUFFIX",
    "LEECH_CAPTION",
    "THUMBNAIL_LAYOUT",
]
uphoster_options = [
    "GOFILE_TOKEN",
    "GOFILE_FOLDER_ID",
    "BUZZHEAVIER_TOKEN",
    "BUZZHEAVIER_FOLDER_ID",
    "PIXELDRAIN_KEY",
]
rclone_options = ["RCLONE_CONFIG", "RCLONE_PATH", "RCLONE_FLAGS"]
gdrive_options = ["TOKEN_PICKLE", "GDRIVE_ID", "INDEX_URL"]
ffset_options = [
    "FFMPEG_CMDS",
    "METADATA",
    "AUDIO_METADATA",
    "VIDEO_METADATA",
    "SUBTITLE_METADATA",
]
advanced_options = [
    "EXCLUDED_EXTENSIONS",
    "NAME_SWAP",
    "YT_DLP_OPTIONS",
    "UPLOAD_PATHS",
    "USER_COOKIE_FILE",
]
yt_options = ["YT_DESP", "YT_TAGS", "YT_CATEGORY_ID", "YT_PRIVACY_STATUS"]

user_settings_text = {
    "THUMBNAIL": (
        "Photo or Doc",
        "Custom Thumbnail is used as the thumbnail for the files you upload to telegram.",
        "<i>Send a photo to save it as custom thumbnail.</i> \n┖ <b>Time Left :</b> <code>60 sec</code>",
    ),
    "RCLONE_CONFIG": (
        "",
        "",
        "<i>Send your <code>rclone.conf</code> file to use as your Upload Dest to RClone.</i> \n┖ <b>Time Left :</b> <code>60 sec</code>",
    ),
    "TOKEN_PICKLE": (
        "",
        "",
        "<i>Send your <code>token.pickle</code> to use as your Upload Dest to GDrive</i> \n┖ <b>Time Left :</b> <code>60 sec</code>",
    ),
    "LEECH_SPLIT_SIZE": (
        "",
        "",
        f"Send Leech split size in bytes or use gb or mb. Example: 40000000 or 2.5gb or 1000mb.</i> \n┖ <b>Time Left :</b> <code>60 sec</code>",
    ),
    "LEECH_DUMP_CHAT": (
        "",
        "",
        "Send leech destination ID/USERNAME/PM.\n┖ <b>Time Left :</b> <code>60 sec</code>",
    ),
    "LEECH_PREFIX": (
        "",
        "",
        "Send Leech Filename Prefix. You can add HTML tags. Example: <code>@mychannel</code>.</i> \n┖ <b>Time Left :</b> <code>60 sec</code>",
    ),
    "LEECH_SUFFIX": (
        "",
        "",
        "Send Leech Filename Suffix. You can add HTML tags. Example: <code>@mychannel</code>.</i> \n┖ <b>Time Left :</b> <code>60 sec</code>",
    ),
    "LEECH_CAPTION": (
        "",
        "",
        "Send Leech Caption. You can add HTML tags. Example: <code>@mychannel</code>.</i> \n┖ <b>Time Left :</b> <code>60 sec</code>",
    ),
    "THUMBNAIL_LAYOUT": (
        "",
        "",
        "Send thumbnail layout (widthxheight, 2x2, 3x3, 2x4, 4x4, ...). Example: 3x3.</i> \n┖ <b>Time Left :</b> <code>60 sec</code>",
    ),
    "EXCLUDED_EXTENSIONS": (
        "",
        "",
        "Send excluded extensions separated by space without dot at beginning. </i> \n┖ <b>Time Left :</b> <code>60 sec</code>",
    ),
    "NAME_SWAP": (
        "",
        "",
        "<i>Send your Name Swap. You can add pattern instead of normal text.</i>\n┖ <b>Time Left :</b> <code>60 sec</code>",
    ),
    "USER_COOKIE_FILE": (
        "File",
        "User's YT-DLP Cookie File to authenticate access to websites and youtube.",
        "<i>Send your cookie file (e.g., cookies.txt or abc.txt).</i> \n┖ <b>Time Left :</b> <code>60 sec</code>",
    ),
    "GOFILE_TOKEN": (
        "",
        "",
        "<i>Send your Gofile API Token.</i> \n┖ <b>Time Left :</b> <code>60 sec</code>",
    ),
    "GOFILE_FOLDER_ID": (
        "",
        "",
        "<i>Send your Gofile Folder ID. If empty, uploads to Root.</i> \n┖ <b>Time Left :</b> <code>60 sec</code>",
    ),
    "BUZZHEAVIER_TOKEN": (
        "",
        "",
        "<i>Send your BuzzHeavier API Token.</i> \n┖ <b>Time Left :</b> <code>60 sec</code>",
    ),
    "BUZZHEAVIER_FOLDER_ID": (
        "",
        "",
        "<i>Send your BuzzHeavier Folder ID.</i> \n┖ <b>Time Left :</b> <code>60 sec</code>",
    ),
    "PIXELDRAIN_KEY": (
        "",
        "",
        "<i>Send your PixelDrain API Key.</i> \n┖ <b>Time Left :</b> <code>60 sec</code>",
    ),
}


async def get_user_data(user_id: int) -> dict:
    if user_id in USER_DATA:
        return USER_DATA[user_id]

    db = get_mongodb_client()
    if db and db.is_connected:
        user_info = await db.get_user(user_id)
        if user_info:
            USER_DATA[user_id] = user_info
            return user_info

    USER_DATA[user_id] = {}
    return USER_DATA[user_id]


async def update_user_ldata(user_id: int, key: str, value: Any):
    if user_id not in USER_DATA:
        await get_user_data(user_id)

    if value == "empty":
        USER_DATA[user_id].pop(key, None)
    else:
        USER_DATA[user_id][key] = value

    db = get_mongodb_client()
    if db and db.is_connected:
        await db.save_user(user_id, USER_DATA[user_id])
