"""Repost every post from a source channel to a target channel, oldest first.

Options (ported + extended from repost_with_stats.py):
- mode "copy":   fresh message from your account, no "Forwarded from" tag
                 (media object handed straight to send_file — no re-upload)
- mode "forward": real Telegram forward, keeps the tag
- send_stats:    a 📊 message before each post (views/forwards/reactions/link)
- delete_original: remove the message(s) from the source after reposting
"""
from __future__ import annotations

import asyncio
from datetime import timezone

from .common import resolve_entity, retry, read_progress, save_progress

TEXT_LIMIT = 4096
CAPTION_LIMIT = 1024


# ------------------------------------------------------------------ helpers

def _post_link(source, msg_id: int) -> str:
    username = getattr(source, "username", None)
    if username:
        return f"https://t.me/{username}/{msg_id}"
    return f"https://t.me/c/{source.id}/{msg_id}"


def _reactions(msg) -> str:
    reactions = getattr(msg, "reactions", None)
    if not reactions or not reactions.results:
        return "none"
    parts = []
    for r in reactions.results:
        emoticon = getattr(r.reaction, "emoticon", None) or "custom"
        parts.append(f"{emoticon} {r.count}")
    return ", ".join(parts)


def _stats_text(source, msg) -> str:
    date_str = (msg.date.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                if msg.date else "N/A")
    return (
        "📊 Post stats\n"
        f"🗓 Date: {date_str}\n"
        f"👁 Views: {msg.views if msg.views is not None else 'N/A'}\n"
        f"🔁 Forwards: {msg.forwards if msg.forwards is not None else 'N/A'}\n"
        f"❤️ Reactions: {_reactions(msg)}\n"
        f"🔗 Original: {_post_link(source, msg.id)}"
    )


def _is_service(msg) -> bool:
    return getattr(msg, "action", None) is not None


def _is_copyable_media(msg) -> bool:
    from telethon.tl.types import MessageMediaWebPage, MessageMediaPoll

    if not msg.media:
        return False
    return not isinstance(msg.media, (MessageMediaWebPage, MessageMediaPoll))


def _chunks(text: str, limit: int):
    return [text[i:i + limit] for i in range(0, len(text), limit)] if text else []


# --------------------------------------------------------------------- tool

async def run_repost(client, p: dict, ctx) -> str:
    """p: source, target, mode ('copy'|'forward'), send_stats, delete_original,
    start_from_id, delay, progress_file"""
    source = await resolve_entity(client, p["source"])
    target = await resolve_entity(client, p["target"])
    ctx.log(f"Source: {getattr(source, 'title', p['source'])}")
    ctx.log(f"Target: {getattr(target, 'title', p['target'])}")

    mode = p.get("mode", "copy")
    send_stats = bool(p.get("send_stats"))
    delete_original = bool(p.get("delete_original"))
    delay = float(p.get("delay") or 1.5)
    progress_file = p["progress_file"]

    start_id = int(p.get("start_from_id") or 0)
    if start_id == 0:
        start_id = read_progress(progress_file)
        if start_id:
            ctx.log(f"Resuming after message ID {start_id} (progress file)")

    total = (await client.get_messages(source, limit=0)).total or 0
    processed = 0

    async def send_copy(msgs: list) -> None:
        """Copy one message or an album without the forward tag."""
        files = [m.media for m in msgs if _is_copyable_media(m)]
        caption = next((m.text for m in msgs if m.text), None)

        if not files:
            for part in _chunks(caption or "", TEXT_LIMIT):
                await retry(ctx, client.send_message, target, part)
            return
        file_arg = files[0] if len(files) == 1 else files
        if caption and len(caption) > CAPTION_LIMIT:
            await retry(ctx, client.send_file, target, file=file_arg)
            for part in _chunks(caption, TEXT_LIMIT):
                await retry(ctx, client.send_message, target, part)
        else:
            await retry(ctx, client.send_file, target,
                        file=file_arg, caption=caption)

    async def handle(msgs: list) -> None:
        nonlocal processed
        first = msgs[0]
        label = (f"album of {len(msgs)} (IDs {msgs[0].id}–{msgs[-1].id})"
                 if len(msgs) > 1 else f"message {first.id}")
        ctx.log(f"Reposting {label}…")

        if send_stats:
            await retry(ctx, client.send_message, target,
                        _stats_text(source, first), link_preview=False)
            await asyncio.sleep(delay)

        if mode == "forward":
            await retry(ctx, client.forward_messages, target,
                        [m.id for m in msgs], source)
        else:
            await send_copy(msgs)

        if delete_original:
            await retry(ctx, client.delete_messages, source,
                        [m.id for m in msgs])
            ctx.log("  → Original deleted from source")

        save_progress(progress_file, msgs[-1].id)
        processed += len(msgs)
        ctx.progress(processed, total)
        await asyncio.sleep(delay)

    pending_gid, pending = None, []

    async def flush() -> None:
        nonlocal pending_gid, pending
        if pending:
            await handle(pending)
        pending_gid, pending = None, []

    async for msg in client.iter_messages(source, min_id=start_id, reverse=True):
        if ctx.cancelled():
            break
        if _is_service(msg) or (not msg.text and not msg.media):
            continue

        if msg.grouped_id:
            if pending_gid is not None and msg.grouped_id != pending_gid:
                await flush()
            pending_gid = msg.grouped_id
            pending.append(msg)
            continue

        await flush()
        await handle([msg])

    if not ctx.cancelled():
        await flush()

    if ctx.cancelled():
        return f"Stopped after {processed} messages (progress saved)"
    return f"Reposted {processed} messages"
