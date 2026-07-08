"""Replace the media and/or caption of specific posts in a channel.

Takes a per-post mapping (post ID -> new image path / new text). For each
post, passing `None` for image or text leaves that side untouched (Telegram
only changes what's actually sent in the edit request), so a post can have
just its image swapped, just its caption rewritten, or both.
"""
from __future__ import annotations

import asyncio

from .common import resolve_entity, retry


async def run_post_image_replace(client, p: dict, ctx) -> str:
    """p: channel, mapping (list of {"id", "image", "text"}), delay"""
    entity = await resolve_entity(client, p["channel"])
    ctx.log(f"Target: {getattr(entity, 'title', p['channel'])}")

    mapping = p["mapping"]
    delay = float(p.get("delay") or 1.0)
    total = len(mapping)
    done = failed = 0

    for i, item in enumerate(mapping, 1):
        if ctx.cancelled():
            break
        msg_id = item["id"]
        kwargs = {}
        if item.get("image"):
            kwargs["file"] = item["image"]
        if item.get("text") is not None:
            kwargs["text"] = item["text"]

        ctx.log(f"Editing message {msg_id}…")
        try:
            result = await retry(ctx, client.edit_message, entity, msg_id, **kwargs)
        except Exception as exc:  # noqa: BLE001 - one bad post shouldn't abort the batch
            result = None
            ctx.log(f"  ! {msg_id}: {exc}")

        if result is None:
            failed += 1
        else:
            done += 1
        ctx.progress(i, total)
        await asyncio.sleep(delay)

    suffix = f", {failed} failed" if failed else ""
    if ctx.cancelled():
        return f"Stopped after editing {done} post(s){suffix}"
    return f"Edited {done} post(s){suffix}"
