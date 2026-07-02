"""Export deleted messages (and media) from a group's admin log.

Ported from the original __main__.py. Notes:
- Telegram's admin log only keeps ~48 hours of events.
- Requires admin rights in the target group/channel.
- Appends JSON objects to <output>/dump.json (comma-separated), media files are
  saved next to it named by message ID — the Restore tool expects this layout.
"""
from __future__ import annotations

import asyncio
import os

from .common import resolve_entity


async def run_backup(client, p: dict, ctx) -> str:
    """p: group, mode (1 all / 2 media / 3 text), min_id, max_id, output_folder"""
    entity = await resolve_entity(client, p["group"])
    ctx.log(f"Group: {getattr(entity, 'title', p['group'])}")

    out = p["output_folder"]
    os.makedirs(out, exist_ok=True)
    dump_path = os.path.join(out, "dump.json")
    mode = int(p["mode"])
    min_id = int(p.get("min_id") or 0)
    max_id = int(p.get("max_id") or 0)

    texts = media = 0
    with open(dump_path, "a", encoding="utf-8") as dump:
        async for event in client.iter_admin_log(entity, delete=True):
            if ctx.cancelled():
                break
            old = getattr(event, "old", None)
            if not getattr(event, "deleted_message", False) or old is None:
                continue
            if min_id and old.id < min_id:
                continue
            if max_id and old.id > max_id:
                continue

            has_media = bool(getattr(old, "media", None))

            if mode in (1, 3) and not (mode == 3 and has_media):
                dump.write(old.to_json() + ",")
                texts += 1
                ctx.log(f"Saved message {texts} "
                        f"(ID {old.id}, {old.date})")

            if mode in (1, 2) and has_media:
                try:
                    await client.download_media(
                        old.media, os.path.join(out, str(old.id))
                    )
                    media += 1
                    ctx.log(f"Saved media {media} (ID {old.id})")
                except Exception as e:  # noqa: BLE001
                    ctx.log(f"  Media download failed for {old.id}: {e}")

            ctx.progress(texts + media, 0)  # total unknown
            await asyncio.sleep(0.1)

    return f"{texts} messages, {media} media files → {out}"
