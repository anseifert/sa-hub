import asyncio

_sync_lock = asyncio.Lock()
_sync_running = False


def is_sync_running() -> bool:
    return _sync_running


async def run_sync_guarded(coro):
    """Run full sync only once at a time."""
    global _sync_running
    async with _sync_lock:
        if _sync_running:
            return False
        _sync_running = True
    try:
        await coro()
        return True
    finally:
        async with _sync_lock:
            _sync_running = False
