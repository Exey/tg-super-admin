"""Repost only the posts inside a group that were themselves forwarded from
one particular author/channel, on to a target channel.

Handy for a chat where members repost from many different sources and you
only want to relay the ones that originated from one of them. Shares the
copy/forward/stats/delete machinery with the plain "Repost channel" tool
(`run_repost`) and adds a matching predicate on top.

`count_repost_group` runs the same filter without touching the target chat,
so you can check the match count and confirm you picked the right
author/source before running the real repost.
"""
from __future__ import annotations

from telethon import utils
from telethon.tl.types import PeerChannel, PeerChat, PeerUser

from .common import resolve_entity
from .repost import run_repost


def _peer_id(peer) -> int | None:
    if isinstance(peer, PeerUser):
        return peer.user_id
    if isinstance(peer, PeerChannel):
        return peer.channel_id
    if isinstance(peer, PeerChat):
        return peer.chat_id
    return None


async def _build_filter(client, author_value: str):
    """Resolve the chosen author/source once and return (predicate, label).

    Matches by ID when Telegram exposes the forward's origin (`fwd_from.from_id`).
    Falls back to a case-insensitive substring match against `fwd_from.from_name`
    for forwards whose original account hides who they're from — Telegram only
    gives a display name in that case, not an ID.
    """
    entity = await resolve_entity(client, author_value)
    target_id = utils.get_peer_id(entity, add_mark=False)
    target_name = author_value.strip().lower()

    def accept(msg) -> bool:
        fwd = getattr(msg, "fwd_from", None)
        if not fwd:
            return False
        if fwd.from_id is not None:
            return _peer_id(fwd.from_id) == target_id
        if fwd.from_name:
            return target_name in fwd.from_name.lower()
        return False

    label = getattr(entity, "title", None) or getattr(entity, "username", None) or author_value
    return accept, label


async def run_repost_group(client, p: dict, ctx) -> str:
    """p: source, target, author, mode ('copy'|'forward'), send_stats,
    delete_original, start_from_id, delay, progress_file"""
    accept, label = await _build_filter(client, p["author"])
    ctx.log(f"Only reposting messages forwarded from: {label}")
    return await run_repost(client, p, ctx, accept=accept)


HEARTBEAT_EVERY = 200  # log a scan heartbeat this often so a big group doesn't look stuck


async def count_repost_group(client, p: dict, ctx) -> str:
    """p: source, author. Read-only: scans the source and reports how many
    messages match the author/source filter, without posting anything."""
    source = await resolve_entity(client, p["source"])
    accept, label = await _build_filter(client, p["author"])
    ctx.log(f"Counting posts forwarded from: {label}")

    total = (await client.get_messages(source, limit=0)).total or 0
    ctx.log(f"Scanning ~{total or 'an unknown number of'} messages…")
    scanned = matched = 0

    async for msg in client.iter_messages(source):
        if ctx.cancelled():
            break
        scanned += 1
        if accept(msg):
            matched += 1
            ctx.log(f"  ✓ match: message {msg.id}")
        if scanned % HEARTBEAT_EVERY == 0:
            ctx.log(f"  …scanned {scanned}/{total or '?'}, {matched} match(es) so far")
        ctx.progress(scanned, total)

    if ctx.cancelled():
        return f"Stopped: {matched} matching post(s) found in {scanned} scanned"
    return f"{matched} matching post(s) out of {scanned} scanned"
