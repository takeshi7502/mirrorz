from asyncio import sleep
from os import listdir

from ... import LOGGER, bot_loop

_monitor_task = None


async def monitor_file_descriptors():
    try:
        from resource import RLIMIT_NOFILE, getrlimit

        soft_limit, _ = getrlimit(RLIMIT_NOFILE)
    except ImportError:
        return
    if soft_limit <= 0:
        return
    previous_level = 0
    while True:
        await sleep(300)
        try:
            used = len(listdir("/proc/self/fd"))
        except OSError as error:
            LOGGER.warning("Failed to inspect file descriptors: %s", error)
            continue
        ratio = used / soft_limit
        level = 2 if ratio >= 0.85 else 1 if ratio >= 0.7 else 0
        if level and level >= previous_level:
            LOGGER.warning(
                "High file descriptor usage: %s/%s (%.0f%%)",
                used,
                soft_limit,
                ratio * 100,
            )
        elif not level and previous_level:
            LOGGER.info("File descriptor usage recovered: %s/%s", used, soft_limit)
        previous_level = level


def start_resource_monitor():
    global _monitor_task
    if _monitor_task is None or _monitor_task.done():
        _monitor_task = bot_loop.create_task(monitor_file_descriptors())
