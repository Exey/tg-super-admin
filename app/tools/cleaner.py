"""Delete ALL messages in a channel/group — except a keep list.

Ported from telegram_cleaner.py, extended:
- `keep_ids`: message IDs that must survive.
- If a kept message belongs to an album (grouped_id, 2-10 media), every
  message sharing that grouped_id is kept too, so albums stay whole.

Confirmation (typed "DELETE") happens in the GUI before this starts.
"""
from __future__ import annotations

import asyncio

from .common import resolve_entity, retry


async def run_cleaner(client, p: dict, ctx) -> str:
    """p: channel, batch_size, keep_ids (list[int])"""
    entity = await resolve_entity(client, p["channel"])
    title = getattr(entity, "title", p["channel"])
    kind = "channel" if getattr(entity, "broadcast", False) else "group"
    ctx.log(f"Target: {title} (ID {entity.id}, {kind})")

    keep_ids: set[int] = {int(i) for i in (p.get("keep_ids") or [])}
    keep_groups: set[int] = set()

    if keep_ids:
        ctx.log(f"Keep list: {sorted(keep_ids)}")
        kept_msgs = await retry(ctx, client.get_messages, entity,
                                ids=list(keep_ids)) or []
        found_ids = set()
        for msg in kept_msgs:
            if msg is None:
                continue
            found_ids.add(msg.id)
            if getattr(msg, "grouped_id", None):
                keep_groups.add(msg.grouped_id)
                ctx.log(f"  ID {msg.id} is part of album {msg.grouped_id} "
                        f"- the whole album will be kept")
        missing = keep_ids - found_ids
        if missing:
            ctx.log(f"  ! Not found in this channel (already deleted?): "
                    f"{sorted(missing)}")

    total = (await client.get_messages(entity, limit=0)).total or 0
    ctx.log(f"Total messages: {total}")
    if total == 0:
        return "Channel is already empty"

    batch = max(1, min(100, int(p.get("batch_size") or 100)))
    deleted = kept = 0
    to_delete: list[int] = []

    async def flush() -> bool:
        nonlocal deleted, to_delete
        if not to_delete:
            return True
        result = await retry(ctx, client.delete_messages, entity, to_delete)
        if result is None:
            return False
        deleted += len(to_delete)
        pct = deleted / total * 100 if total else 0
        ctx.log(f"Deleted {deleted}/{total} ({pct:.1f}%)")
        ctx.progress(min(deleted + kept, total), total)
        to_delete = []
        await asyncio.sleep(1)
        return True

    async for msg in client.iter_messages(entity):
        if ctx.cancelled():
            break
        gid = getattr(msg, "grouped_id", None)
        if msg.id in keep_ids or (gid and gid in keep_groups):
            kept += 1
            ctx.log(f"  Keeping message {msg.id}"
                    + (f" (album {gid})" if gid else ""))
            continue
        to_delete.append(msg.id)
        if len(to_delete) >= batch:
            if not await flush():
                break

    if not ctx.cancelled():
        await flush()

    suffix = f", kept {kept}" if kept else ""
    if ctx.cancelled():
        return f"Stopped after deleting {deleted} messages{suffix}"
    return f"Deleted {deleted} messages{suffix}"
