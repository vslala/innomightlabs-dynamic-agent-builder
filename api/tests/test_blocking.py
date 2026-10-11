"""Running a coroutine from sync code, with and without an event loop already running."""

import asyncio

from src.common.blocking import run_blocking


async def _answer() -> int:
    await asyncio.sleep(0)
    return 42


def test_runs_a_coroutine_from_plain_sync_code():
    assert run_blocking(_answer()) == 42


async def test_runs_a_coroutine_while_an_event_loop_is_already_running():
    """The case that matters: sync form code reached from an async route."""
    assert run_blocking(_answer()) == 42


def test_raises_what_the_coroutine_raises():
    async def fail() -> None:
        raise ValueError("boom")

    try:
        run_blocking(fail())
    except ValueError as e:
        assert str(e) == "boom"
    else:
        raise AssertionError("expected ValueError")
