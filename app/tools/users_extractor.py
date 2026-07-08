"""Fetch the member lists of two groups so the GUI can diff them.

Both member lists are fetched once and returned to the GUI as JSON; the GUI
then computes (and lets the user switch between) "in A not B", "in B not A",
intersection and symmetric-difference views locally, without re-fetching.
"""
from __future__ import annotations

import json

from .common import resolve_entity

HEARTBEAT_EVERY = 200


def _member_dict(user) -> dict:
    name = " ".join(filter(None, [
        getattr(user, "first_name", None), getattr(user, "last_name", None),
    ])).strip()
    username = getattr(user, "username", None)
    return {
        "id": user.id,
        "username": username,
        "name": name or (f"@{username}" if username else str(user.id)),
    }


async def _fetch_members(client, ctx, value: str, label: str) -> tuple[str, list[dict]]:
    entity = await resolve_entity(client, value)
    title = str(getattr(entity, "title", value))
    try:
        total = (await client.get_participants(entity, limit=0)).total or 0
    except Exception:
        total = 0
    ctx.log(f"{label}: {title} (~{total or 'unknown'} member(s))")

    members: list[dict] = []
    scanned = 0
    async for user in client.iter_participants(entity):
        if ctx.cancelled():
            break
        scanned += 1
        members.append(_member_dict(user))
        if scanned % HEARTBEAT_EVERY == 0:
            ctx.log(f"  {label}: scanned {scanned}/{total or '?'}")
        ctx.progress(scanned, total)
    return title, members


async def run_users_extractor(client, p: dict, ctx) -> str:
    """p: group_a, group_b"""
    title_a, members_a = await _fetch_members(client, ctx, p["group_a"], "A")
    if not ctx.cancelled():
        title_b, members_b = await _fetch_members(client, ctx, p["group_b"], "B")
    else:
        title_b, members_b = "", []

    ctx.log(f"Group A '{title_a}': {len(members_a)} member(s). "
            f"Group B '{title_b}': {len(members_b)} member(s).")
    return json.dumps({
        "cancelled": ctx.cancelled(),
        "a": {"title": title_a, "members": members_a},
        "b": {"title": title_b, "members": members_b},
    })
