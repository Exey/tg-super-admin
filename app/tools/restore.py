"""Send a backup (dump.json + downloaded media) into a chat / forum topic.

Ported from send_media_to_topic_advanced.py. Forwards albums by original IDs
where possible, otherwise re-sends local media files / plain text.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime

from .common import resolve_entity, retry, read_progress, save_progress


# ------------------------------------------------------------- dump parsing

def _extract_all_json_objects(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    decoder = json.JSONDecoder()
    idx, objects = 0, []
    while idx < len(content):
        try:
            obj, end = decoder.raw_decode(content, idx)
            objects.append(obj)
            idx = end
            while idx < len(content) and content[idx] in " \t\n\r,":
                idx += 1
        except json.JSONDecodeError:
            idx += 1
    return objects


def load_messages(json_path: str) -> list:
    if not os.path.exists(json_path):
        return []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "messages" in data:
            return data["messages"]
        return [data]
    except json.JSONDecodeError:
        pass
    messages = []
    for obj in _extract_all_json_objects(json_path):
        if isinstance(obj, list):
            messages.extend(obj)
        elif isinstance(obj, dict):
            messages.extend(obj.get("messages", [])) if "messages" in obj \
                else messages.append(obj)
    return messages


# ---------------------------------------------------------- message helpers

def _text(msg) -> str:
    return msg.get("message") or msg.get("text") or ""


def _has_media(msg) -> bool:
    media = msg.get("media")
    return media is not None and media != {}


def _media_size_mb(msg) -> float:
    media = msg.get("media") or {}
    if media.get("_") == "MessageMediaDocument":
        doc = media.get("document") or {}
        if "size" in doc:
            return doc["size"] / (1024 * 1024)
    return 0.0


def _from_peer(msg):
    fwd = msg.get("fwd_from")
    if isinstance(fwd, dict):
        from_id = fwd.get("from_id")
        if isinstance(from_id, dict):
            if from_id.get("_") == "PeerChannel":
                return int(f"-100{from_id['channel_id']}")
            if from_id.get("_") == "PeerUser":
                return from_id["user_id"]
        elif from_id:
            return from_id
    peer = msg.get("peer_id")
    if isinstance(peer, dict):
        if peer.get("_") == "PeerChannel":
            return int(f"-100{peer['channel_id']}")
        if peer.get("_") == "PeerUser":
            return peer["user_id"]
    return None


def _original_id(msg):
    fwd = msg.get("fwd_from")
    if fwd:
        return fwd.get("channel_post") or fwd.get("saved_from_msg_id")
    return msg.get("id")


def _date_only(msg):
    date_str = msg.get("date", "")
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(
            date_str.replace("Z", "+00:00")
        ).strftime("%Y-%m-%d")
    except ValueError:
        return None


# -------------------------------------------------------------------- tool

async def run_restore(client, p: dict, ctx) -> str:
    """p: backup_folder, chat, topic_id, daily_separator, max_size_mb,
    skip_big, start_index, search_text, delay, progress_file"""
    from telethon.tl.functions.messages import ForwardMessagesRequest

    folder = p["backup_folder"]
    json_path = os.path.join(folder, "dump.json")
    messages = load_messages(json_path)
    if not messages:
        return "No messages found in dump.json"
    messages.sort(key=lambda x: x.get("date", ""))
    total = len(messages)
    ctx.log(f"Loaded {total} messages from {json_path}")

    entity = await resolve_entity(client, p["chat"])
    topic_id = int(p.get("topic_id") or 0) or None
    delay = float(p.get("delay") or 1.0)
    max_mb = float(p.get("max_size_mb") or 50)
    skip_big = bool(p.get("skip_big"))
    daily_sep = bool(p.get("daily_separator"))
    progress_file = p["progress_file"]

    start = int(p.get("start_index") or 0)
    search = (p.get("search_text") or "").lower().strip() or None
    if search:
        found = next((i for i, m in enumerate(messages)
                      if search in _text(m).lower()), -1)
        if found == -1:
            return f"Text '{search}' not found in dump"
        start = found + 1
        ctx.log(f"Found text at message {found + 1}, starting from {start}")
    elif start == 0:
        start = read_progress(progress_file)
        if start:
            ctx.log(f"Resuming from index {start} (progress file)")
    if start >= total:
        return f"Start index {start} >= total {total}, nothing to do"

    reply_to = topic_id

    async def send_text(text: str) -> None:
        if text:
            await retry(ctx, client.send_message, entity,
                        message=text, reply_to=reply_to)

    async def send_separator(date_str: str) -> None:
        await send_text(f"---= {date_str} =---")
        ctx.log(f"  → Separator: {date_str}")

    async def forward_group(from_peer, ids: list) -> None:
        ids = ids[:10]
        if not ids:
            return
        ctx.log(f"  → Forwarding album of {len(ids)} from {from_peer}")
        try:
            await retry(ctx, client, ForwardMessagesRequest(
                from_peer=from_peer, id=ids,
                to_peer=entity, top_msg_id=reply_to,
            ))
        except Exception as e:  # noqa: BLE001
            ctx.log(f"  → Album forward failed: {e}. One by one…")
            for mid in ids:
                try:
                    await retry(ctx, client, ForwardMessagesRequest(
                        from_peer=from_peer, id=[mid],
                        to_peer=entity, top_msg_id=reply_to,
                    ))
                except Exception as e2:  # noqa: BLE001
                    ctx.log(f"    → Could not forward {mid}: {e2}")

    async def send_local_media(msg) -> None:
        msg_id = msg.get("id")
        text = _text(msg)
        media_file = None
        if _has_media(msg) and os.path.isdir(folder):
            for fname in os.listdir(folder):
                if fname.startswith(str(msg_id)) and fname != "dump.json":
                    media_file = os.path.join(folder, fname)
                    break
        if media_file:
            await retry(ctx, client.send_file, entity, file=media_file,
                        caption=text, reply_to=reply_to, force_document=False)
            ctx.log("  → Sent local media + text")
        elif text:
            await send_text(text)

    # last date already sent (for the separator)
    last_date = None
    if daily_sep and start > 0:
        for j in range(min(start, total)):
            d = _date_only(messages[j])
            if d:
                last_date = d

    i = start
    current_from, buffer_ids = None, []

    async def flush() -> None:
        nonlocal current_from, buffer_ids
        if buffer_ids:
            await forward_group(current_from, buffer_ids)
        current_from, buffer_ids = None, []

    while i < total and not ctx.cancelled():
        msg = messages[i]
        date = _date_only(msg)
        if daily_sep and date and date != last_date:
            await flush()
            await send_separator(date)
            last_date = date
            await asyncio.sleep(delay)

        from_peer = _from_peer(msg)
        has_media = _has_media(msg)
        text = _text(msg)

        if not has_media and not text:
            ctx.log(f"[{i + 1}/{total}] Empty, skipped")
            await flush()
        elif not from_peer:
            ctx.log(f"[{i + 1}/{total}] No source peer, sending as new")
            await flush()
            await send_local_media(msg)
        elif not has_media:
            ctx.log(f"[{i + 1}/{total}] Text message")
            await flush()
            await send_text(text)
        elif _media_size_mb(msg) > max_mb:
            size = _media_size_mb(msg)
            await flush()
            if skip_big:
                ctx.log(f"[{i + 1}/{total}] Media {size:.1f} MB > limit, "
                        f"skipping whole message")
            else:
                ctx.log(f"[{i + 1}/{total}] Media {size:.1f} MB > limit, "
                        f"text only")
                await send_text(text)
        else:
            # buffer media for album forwarding
            oid = _original_id(msg)
            if current_from is None:
                current_from, buffer_ids = from_peer, [oid]
            elif current_from == from_peer:
                buffer_ids.append(oid)
            else:
                await flush()
                current_from, buffer_ids = from_peer, [oid]
            if len(buffer_ids) >= 10:
                await flush()

        save_progress(progress_file, i + 1)
        ctx.progress(i + 1, total)
        i += 1
        await asyncio.sleep(delay)

    await flush()
    if ctx.cancelled():
        return f"Stopped at index {i}/{total} (progress saved)"
    return f"Sent {total - start} messages to chat"
