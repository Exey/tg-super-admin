"""Helpers shared by all tools."""
from __future__ import annotations

import asyncio
import os


async def retry(ctx, coro, *args, **kwargs):
    """Call coro(*args, **kwargs) with FloodWait / transient-error retries."""
    from telethon import errors

    for attempt in range(10):
        if ctx.cancelled():
            return None
        try:
            return await coro(*args, **kwargs)
        except errors.FloodWaitError as e:
            ctx.log(f"  FloodWait: sleeping {e.seconds}s…")
            await _sleep_cancellable(ctx, e.seconds)
        except (ConnectionError, OSError, asyncio.TimeoutError) as e:
            wait = 5 * (attempt + 1)
            ctx.log(f"  Transient error: {e}. Retrying in {wait}s "
                    f"({attempt + 1}/10)…")
            await _sleep_cancellable(ctx, wait)
    ctx.log("  Giving up after 10 attempts.")
    return None


async def _sleep_cancellable(ctx, seconds: float) -> None:
    end = asyncio.get_event_loop().time() + seconds
    while asyncio.get_event_loop().time() < end:
        if ctx.cancelled():
            return
        await asyncio.sleep(min(0.5, seconds))


async def resolve_entity(client, value):
    """Accepts @username, t.me link, or numeric ID (incl. -100… form)."""
    from telethon.tl.types import PeerChannel

    v = str(value).strip()
    if not v:
        raise ValueError("Empty channel/chat identifier")
    try:
        num = int(v)
    except ValueError:
        return await client.get_entity(v)
    try:
        return await client.get_entity(num)
    except Exception:
        s = str(num)
        if s.startswith("-100"):
            return await client.get_entity(PeerChannel(int(s[4:])))
        raise


def read_progress(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0


def save_progress(path: str, value: int) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(value))


def reset_progress(path: str) -> bool:
    if os.path.exists(path):
        os.remove(path)
        return True
    return False
