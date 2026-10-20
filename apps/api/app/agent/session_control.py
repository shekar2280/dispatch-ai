import asyncio


async def until_stopped(operation, stop, timeout):
    """Cancel startup/playout immediately when the call terminates."""
    task = asyncio.ensure_future(operation)
    stopped = asyncio.create_task(stop.wait())
    try:
        done, _ = await asyncio.wait({task, stopped}, timeout=timeout,
                                     return_when=asyncio.FIRST_COMPLETED)
        if stopped in done:
            return False
        if task not in done:
            raise TimeoutError("Voice operation exceeded its deadline")
        await task
        return True
    finally:
        for pending in (task, stopped):
            if not pending.done():
                pending.cancel()
        await asyncio.gather(task, stopped, return_exceptions=True)
