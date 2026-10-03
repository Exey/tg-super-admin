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
        "bot": bool(getattr(user, "bot", False)),
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


ADD_DELAY = 3.0  # seconds between invites — inviting is flood-limited hard


async def add_users_to_group(client, p: dict, ctx) -> str:
    """p: group_b, users (list of member dicts from `_member_dict`).

    Tries to add each user directly to group B (no invite link involved).
    Per user the outcome is:
    - added — invited (or was already a member);
    - need_link — Telegram refused because of the user's privacy settings
      (or no mutual contact), so they can only join via a link;
    - failed — any other error (can't resolve the user, not enough rights…).
    A FloodWait stops the whole batch (waiting it out inline can mean
    hours); everything not yet attempted is left out of all three lists, so
    the caller can simply press the button again later.
    """
    import asyncio

    from telethon import errors
    from telethon.tl.functions.channels import InviteToChannelRequest
    from telethon.tl.functions.messages import AddChatUserRequest
    from telethon.tl.types import Channel

    entity = await resolve_entity(client, p["group_b"])
    users = list(p.get("users") or [])
    is_channel = isinstance(entity, Channel)
    ctx.log(f"Adding {len(users)} user(s) to "
            f"'{getattr(entity, 'title', p['group_b'])}'…")

    added: list[dict] = []
    need_link: list[dict] = []
    failed: list[dict] = []
    stopped_reason: str | None = None

    for i, u in enumerate(users, 1):
        if ctx.cancelled():
            break
        try:
            user = await client.get_input_entity(u["id"])
            if is_channel:
                await client(InviteToChannelRequest(entity, [user]))
            else:
                await client(AddChatUserRequest(entity.id, user, fwd_limit=0))
            added.append(u)
        except errors.UserAlreadyParticipantError:
            added.append(u)
        except (errors.UserPrivacyRestrictedError, errors.UserNotMutualContactError):
            need_link.append(u)
        except errors.FloodWaitError as e:
            from datetime import datetime, timedelta
            ends = (datetime.now() + timedelta(seconds=e.seconds)).strftime("%H:%M")
            stopped_reason = (f"Telegram's flood limit kicked in — wait "
                              f"~{e.seconds // 60 + 1} min (ends at {ends}) "
                              f"and press the button again for the rest.")
            break
        except Exception as e:  # noqa: BLE001 - reported per user
            ctx.log(f"  ! {u.get('username') or u['id']}: {type(e).__name__}: {e}")
            failed.append(u)
        ctx.progress(i, len(users))
        if i < len(users):
            await asyncio.sleep(ADD_DELAY)

    ctx.log(f"Added {len(added)}, need a link {len(need_link)}, "
            f"failed {len(failed)}.")
    if stopped_reason:
        ctx.log(f"  Stopped early: {stopped_reason}")
    return json.dumps({
        "cancelled": ctx.cancelled(),
        "added": added,
        "need_link": need_link,
        "failed": failed,
        "stopped_reason": stopped_reason,
    })
