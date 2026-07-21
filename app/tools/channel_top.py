"""Rank a channel's posts by engagement and return the best ones.

Scans every post (up to an optional limit), reading the stats that ride
along for free with each message — views, total reactions and forwards
("private reposts") — then keeps a candidate pool: the union of the top-N
posts by each of those metrics, so the GUI can re-sort by any column and
still be showing the true leaders.

Album posts (grouped_id, 2-10 photos/videos sent together) collapse into a
single row instead of one row per image — see the merge logic in
run_channel_top.

"Public reposts" (how many *public* channels forwarded a post, and which
ones) are not part of a message object — each needs a separate
stats.GetMessagePublicForwards call — so they're fetched only for the
candidate pool, and only when the user asks for them (fetch_public).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from .common import resolve_entity

HEARTBEAT_EVERY = 500

# Period-of-analysis choices offered in the GUI, in calendar days.
PERIOD_DAYS = {"3m": 90, "6m": 182, "1y": 365, "2y": 730, "3y": 1095}


def period_cutoff(period: str) -> datetime | None:
    """UTC cutoff for a period key, or None for an unrecognized/empty key
    (meaning "no limit" — scan the whole channel)."""
    days = PERIOD_DAYS.get(period)
    return datetime.now(timezone.utc) - timedelta(days=days) if days else None


def _reaction_total(msg) -> int:
    reactions = getattr(msg, "reactions", None)
    if not reactions or not getattr(reactions, "results", None):
        return 0
    return sum(int(getattr(rc, "count", 0) or 0) for rc in reactions.results)


def _preview(text: str, limit: int = 140) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def _public_forwards(client, input_channel, msg_id: int) -> dict:
    """Return {'count': int, 'items': [{title, link, views}]} for one post,
    or {'count': -1, 'items': []} if stats aren't available for this channel."""
    from telethon.tl.functions.stats import GetMessagePublicForwardsRequest
    from telethon.tl.types import PublicForwardMessage

    try:
        res = await client(GetMessagePublicForwardsRequest(
            channel=input_channel, msg_id=msg_id, offset="", limit=100))
    except Exception:
        return {"count": -1, "items": []}

    chats_by_id = {c.id: c for c in getattr(res, "chats", [])}
    items: list[dict] = []
    for fwd in getattr(res, "forwards", []):
        if not isinstance(fwd, PublicForwardMessage):
            continue
        m = fwd.message
        cid = getattr(getattr(m, "peer_id", None), "channel_id", None)
        chat = chats_by_id.get(cid)
        title = str(getattr(chat, "title", None) or cid or "?")
        username = getattr(chat, "username", None)
        if username:
            link = f"https://t.me/{username}/{m.id}"
        elif cid:
            link = f"https://t.me/c/{cid}/{m.id}"
        else:
            link = ""
        items.append({"title": title, "link": link,
                      "views": int(getattr(m, "views", 0) or 0)})
    count = int(getattr(res, "count", len(items)) or len(items))
    return {"count": count, "items": items}


def _top_ids(rows: list[dict], key: str, n: int) -> set[int]:
    ranked = sorted(rows, key=lambda r: r[key], reverse=True)
    return {r["id"] for r in ranked[:n]}


async def _count_since(client, entity, cutoff: datetime | None) -> int:
    """Server-computed message count, no per-message fetching.

    `min_id`/`max_id` on GetHistory are resolved server-side into a count
    (`limit=0` -> `.total`), so this is two cheap calls even on a channel
    with years of history: one to find the ID right before the cutoff
    (`offset_date` is exclusive — "messages previous to this date"), one to
    count everything newer than that ID.
    """
    if cutoff is None:
        return (await client.get_messages(entity, limit=0)).total or 0
    boundary = await client.get_messages(entity, limit=1, offset_date=cutoff)
    min_id = boundary[0].id if boundary else 0
    return (await client.get_messages(entity, limit=0, min_id=min_id)).total or 0


async def count_posts_in_period(client, p: dict, ctx) -> str:
    """p: channel, period. Read-only: reports how many posts fall in the
    chosen period so the GUI can show it next to the period switcher before
    a full scan runs."""
    entity = await resolve_entity(client, p["channel"])
    cutoff = period_cutoff(p.get("period") or "")
    count = await _count_since(client, entity, cutoff)
    ctx.log(f"{count} post(s) in the selected period.")
    return json.dumps({"count": count})


async def run_channel_top(client, p: dict, ctx) -> str:
    """p: channel, top_n, period (PERIOD_DAYS key, '' = all time), fetch_public (bool)."""
    top_n = int(p.get("top_n") or 20)
    cutoff = period_cutoff(p.get("period") or "")
    fetch_public = bool(p.get("fetch_public"))

    entity = await resolve_entity(client, p["channel"])
    title = str(getattr(entity, "title", p["channel"]))
    try:
        total = await _count_since(client, entity, cutoff)
    except Exception:
        total = 0
    ctx.log(f"Scanning '{title}' ({total or 'unknown'} post(s))…")

    rows: list[dict] = []
    scanned = 0
    current: dict | None = None   # album row currently being accumulated
    current_gid = None
    async for msg in client.iter_messages(entity):
        if ctx.cancelled():
            break
        if cutoff and msg.date and msg.date < cutoff:
            break  # iter_messages is newest -> oldest, so we're done
        scanned += 1
        if getattr(msg, "action", None) is not None:
            continue  # skip service messages (joins, pins, …)

        gid = getattr(msg, "grouped_id", None)
        text = _preview(getattr(msg, "message", "") or "")
        views = int(getattr(msg, "views", 0) or 0)
        reactions = _reaction_total(msg)
        forwards = int(getattr(msg, "forwards", 0) or 0)

        if gid is not None and gid == current_gid:
            # Same album as the row being built. Telegram delivers a
            # grouped post as one message per photo/video with consecutive
            # IDs and (usually) identical views/forwards, and puts the
            # caption on only one of them — so merge into a single row
            # instead of listing every image separately.
            current["ids"].append(msg.id)
            current["id"] = msg.id  # keeps shrinking -> ends up = min(ids)
            current["views"] = max(current["views"], views)
            current["reactions"] = max(current["reactions"], reactions)
            current["forwards"] = max(current["forwards"], forwards)
            if not current["text"] and text:
                current["text"] = text
        else:
            current = {
                "id": msg.id,
                "ids": [msg.id],
                "ts": int(msg.date.timestamp()) if msg.date else 0,
                "date": msg.date.isoformat() if msg.date else "",
                "text": text,
                "views": views,
                "reactions": reactions,
                "forwards": forwards,
                "public": None,  # filled below for the pool only
            }
            current_gid = gid
            rows.append(current)

        if scanned % HEARTBEAT_EVERY == 0:
            ctx.log(f"  scanned {scanned}/{total or '?'}…")
        ctx.progress(scanned, total)

    ctx.log(f"Read stats for {len(rows)} post(s) ({scanned} message(s) scanned).")

    # Candidate pool = union of the top-N by each metric, so every sortable
    # column in the GUI still shows the genuine leaders, not just a re-order
    # of the top-by-views slice.
    pool_ids: set[int] = set()
    for key in ("views", "reactions", "forwards"):
        pool_ids |= _top_ids(rows, key, top_n)
    pool = [r for r in rows if r["id"] in pool_ids]
    pool.sort(key=lambda r: r["views"], reverse=True)

    if fetch_public and pool and not ctx.cancelled():
        input_channel = await client.get_input_entity(entity)
        ctx.log(f"Fetching public reposts for {len(pool)} post(s)…")
        unavailable = False
        for i, r in enumerate(pool, 1):
            if ctx.cancelled():
                break
            r["public"] = await _public_forwards(client, input_channel, r["id"])
            if r["public"]["count"] < 0:
                unavailable = True
            ctx.progress(i, len(pool))
        if unavailable:
            ctx.log("  Public-repost stats are unavailable for this channel "
                    "(needs a channel where you can view statistics).")

    return json.dumps({
        "cancelled": ctx.cancelled(),
        "title": title,
        "scanned": len(rows),
        "rows": pool,
    })
