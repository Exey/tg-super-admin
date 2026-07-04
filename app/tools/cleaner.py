"""Delete ALL messages in a channel/group — except a keep list.

Ported from telegram_cleaner.py, extended:
- `keep_ids`: message IDs that must survive.
- If a kept message belongs to an album (grouped_id, 2-10 media), every
  message sharing that grouped_id is kept too, so albums stay whole.

Confirmation (typed "DELETE") happens in the GUI before this starts.
"""
from __future__ import annotations

import asyncio
import json

from .common import resolve_entity, retry

ALBUM_SPAN = 9  # Telegram albums max out at 10 items -> +/-9 IDs covers any album


async def scan_keep_candidates(client, p: dict, ctx) -> str:
    """p: channel, ids (list[int]) — read-only preview for the Cleaner's
    "Add from list": fetches each message, collapses whole albums into a
    single entry (by scanning the neighboring IDs for a shared grouped_id),
    and returns a JSON blob {"cancelled": bool, "items": [...]} for the GUI
    to show in a check-list dialog before anything is added to the keep list.
    """
    channel = await resolve_entity(client, p["channel"])
    requested = sorted({int(i) for i in p["ids"]})
    total = len(requested)
    ctx.log(f"Fetching {total} message(s) from "
            f"{getattr(channel, 'title', p['channel'])}…")

    items: list[dict] = []
    handled: set[int] = set()

    for i, msg_id in enumerate(requested, 1):
        if ctx.cancelled():
            break
        if msg_id in handled:
            ctx.progress(i, total)
            continue

        msg = await retry(ctx, client.get_messages, channel, ids=msg_id)
        if msg is None:
            items.append({"ids": [msg_id], "text": "not found (deleted or wrong ID)",
                         "range": ""})
            handled.add(msg_id)
            ctx.progress(i, total)
            continue

        album_ids = [msg_id]
        if msg.grouped_id:
            lo, hi = max(1, msg_id - ALBUM_SPAN), msg_id + ALBUM_SPAN
            neighbors = await retry(ctx, client.get_messages, channel,
                                    ids=list(range(lo, hi + 1))) or []
            album_ids = sorted(m.id for m in neighbors
                               if m is not None and m.grouped_id == msg.grouped_id)

        handled.update(album_ids)
        text = (msg.text or "").strip().replace("\n", " ")
        if len(text) > 140:
            text = text[:140] + "…"
        if not text:
            text = "(media, no caption)" if msg.media else "(empty message)"

        items.append({
            "ids": album_ids,
            "text": text,
            "range": (f"{album_ids[0]}–{album_ids[-1]} · {len(album_ids)} items"
                      if len(album_ids) > 1 else ""),
        })
        ctx.progress(i, total)

    return json.dumps({"cancelled": ctx.cancelled(), "items": items})


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
