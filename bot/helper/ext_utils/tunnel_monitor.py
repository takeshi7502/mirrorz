from asyncio import Lock, sleep
from os import environ

from aiofiles import open as aiopen
from aiofiles.os import path as aiopath

from ... import LOGGER, bot_loop
from ...core.config_manager import Config
from .db_handler import database


TUNNEL_URL_FILE = environ.get("TUNNEL_URL_FILE", "/data/tunnel_url.txt")
_last_persisted_url = None
_update_lock = Lock()
_monitor_task = None


async def _read_tunnel_url():
    try:
        if not await aiopath.isfile(TUNNEL_URL_FILE):
            return None
        async with aiopen(TUNNEL_URL_FILE, "r") as f:
            url = (await f.read()).strip()
        return url or None
    except Exception as e:
        LOGGER.warning(f"tunnel_monitor: read failed: {e}")
        return None


async def _apply_tunnel_url(url):
    global _last_persisted_url
    url = str(url or "").strip().rstrip("/")
    if not url:
        return False
    async with _update_lock:
        changed = Config.BASE_URL != url
        if changed:
            Config.BASE_URL = url
            LOGGER.info("tunnel_monitor: BASE_URL = %s", url)
        if not database._return and _last_persisted_url != url:
            try:
                await database.update_config({"BASE_URL": url})
            except Exception as error:
                LOGGER.warning("tunnel_monitor: database update failed: %s", error)
            else:
                _last_persisted_url = url
        return changed


async def _tunnel_monitor_loop():
    LOGGER.info("tunnel_monitor: started")
    while True:
        try:
            url = await _read_tunnel_url()
            await _apply_tunnel_url(url)
        except Exception as e:
            LOGGER.error(f"tunnel_monitor: {e}")
        await sleep(5)


async def apply_tunnel_url_once():
    url = await _read_tunnel_url()
    await _apply_tunnel_url(url)
    return url


def start_tunnel_monitor():
    global _monitor_task
    if _monitor_task is None or _monitor_task.done():
        _monitor_task = bot_loop.create_task(_tunnel_monitor_loop())
        LOGGER.info("tunnel_monitor: background monitor started")
    return _monitor_task
