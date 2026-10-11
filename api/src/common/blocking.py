"""Running async code from sync code."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")


def run_blocking(coroutine: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine to completion and return its result, from plain sync code.

    Many sync call chains (form options, model catalogs) are reached from async routes,
    where `asyncio.run` refuses to start inside the running loop. Then the coroutine runs
    on a worker thread with its own loop; the caller waits, as it already does for
    the sync HTTP and DynamoDB calls around it.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coroutine).result()
