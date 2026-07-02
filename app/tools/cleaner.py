"""Delete ALL messages in a channel/group.

Ported from telegram_cleaner.py. Confirmation happens in the GUI (typed
"DELETE") before this coroutine ever starts.
"""
from __future__ import annotations

import asyncio

from .common import resolve_entity, retry


async def run_cleaner(client, p: dict, ctx) -> str:
    """p: channel, batch_size"""
    entity = await resolve_entity(client, p["channel"])
    title = getattr(entity, "title", p["channel"])
    kind = "channel" if getattr(entity, "broadcast", False) else "group"
    ctx.log(f"Target: {title} (ID {entity.id}, {kind})")

    total = (await client.get_messages(entity, limit=0)).total or 0
    ctx.log(f"Total messages: {total}")
    if total == 0:
        return "Channel is already empty"

    batch = max(1, int(p.get("batch_size") or 100))
    deleted = 0

    while not ctx.cancelled():
        msgs = await retry(ctx, client.get_messages, entity, limit=batch)
        if not msgs:
            break
        ids = [m.id for m in msgs]
        result = await retry(ctx, client.delete_messages, entity, ids)
        if result is None:  # gave up after retries
            break
        deleted += len(ids)
        pct = deleted / total * 100 if total else 0
        ctx.log(f"Deleted {deleted}/{total} ({pct:.1f}%)")
        ctx.progress(min(deleted, total), total)
        await asyncio.sleep(1)

    if ctx.cancelled():
        return f"Stopped after deleting {deleted} messages"
    return f"Deleted {deleted} messages"
