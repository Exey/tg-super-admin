"""Analyze a Telegram Desktop chat export (result.json) for sender
activity — no Telegram connection involved, this only reads a local file.

Export format: https://core.telegram.org/import-export. The relevant shape
is `{"name": ..., "messages": [{"type": "message"|"service", "date_unixtime":
..., "from": ..., "from_id": ..., ...}, ...]}`. Only `type == "message"`
entries count as "wrote a message" — service entries (joins, pins, title
changes, …) are attributed to an `actor`, not authored content, so they're
skipped.

`analyze_export` does one pass over `messages`, counting per-sender message
totals and per-sender message dates. From that:
- how many distinct senders posted at least once within each of a fixed set
  of trailing windows (last week / month / 3 months / 6 months / year) plus
  all-time — a sender with no parseable date only counts toward all-time,
  since there's no way to place them in a narrower window;
- which senders sent exactly one message, all-time.

`run_chat_activity` is the entry point a `LocalTaskWorker` calls; it wraps
`analyze_export` with progress/cancellation reporting and returns the
summary as JSON, matching the rest of the app's tool-function convention
(structured data out, the tab builds the Markdown report from it).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

# (key, label, days) — order matters, it's the report's row order. "all"
# has no day count: every sender with at least one message counts.
PERIODS: list[tuple[str, str, int | None]] = [
    ("week", "Last week", 7),
    ("month", "Last month", 30),
    ("3m", "3 months", 90),
    ("6m", "6 months", 182),
    ("year", "1 year", 365),
    ("all", "All time", None),
]

HEARTBEAT_EVERY = 20_000


def _sender_key(msg: dict) -> tuple[str, str] | None:
    """(id, display_name) for a message's author, or None if `msg` isn't a
    regular authored message (a service entry, or missing both from/from_id)."""
    if msg.get("type") != "message":
        return None
    sender_id = msg.get("from_id")
    name = msg.get("from")
    if not sender_id and not name:
        return None
    if not sender_id:
        # Very old export format sometimes omits from_id — group by name
        # instead of dropping the message.
        sender_id = f"name:{name}"
    return str(sender_id), str(name or sender_id)


def _msg_datetime(msg: dict) -> datetime | None:
    ts = msg.get("date_unixtime")
    if ts is not None:
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            pass
    date_str = msg.get("date")
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def analyze_export(path: str, ctx=None, now: datetime | None = None) -> dict:
    """Reads and analyzes one chat export JSON file. `ctx` (optional) gets
    progress/log/cancellation callbacks, matching the app's Ctx/LocalCtx
    shape. Returns a summary dict — see `run_chat_activity` for its shape."""
    now = now or datetime.now(timezone.utc)

    if ctx:
        ctx.log(f"Reading {path}…")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    messages = data.get("messages") or []
    chat_name = str(data.get("name") or Path(path).stem)
    total_in_file = len(messages)
    if ctx:
        ctx.log(f"Loaded '{chat_name}' — {total_in_file} entries. Counting senders…")

    counts: dict[str, int] = {}
    names: dict[str, str] = {}
    last_dates: dict[str, datetime] = {}  # most recent message per sender is
    # enough to place them in every window — a sender active this week is by
    # definition also active this month/3mo/etc, so tracking only the max
    # date (not every date) is both correct and far cheaper than a full list.
    no_date_senders: set[str] = set()
    counted = 0

    for i, msg in enumerate(messages, 1):
        if ctx and ctx.cancelled():
            break
        parsed = _sender_key(msg)
        if parsed is not None:
            key, name = parsed
            counts[key] = counts.get(key, 0) + 1
            names.setdefault(key, name)
            dt = _msg_datetime(msg)
            if dt is not None:
                if key not in last_dates or dt > last_dates[key]:
                    last_dates[key] = dt
            else:
                no_date_senders.add(key)
            counted += 1
        if ctx and i % HEARTBEAT_EVERY == 0:
            ctx.log(f"  scanned {i}/{total_in_file}…")
            ctx.progress(i, total_in_file)
    if ctx:
        ctx.progress(total_in_file, total_in_file)

    active_by_period: dict[str, int] = {}
    for key, _label, days in PERIODS:
        if days is None:
            active_by_period[key] = len(counts)
            continue
        cutoff = now - timedelta(days=days)
        active_by_period[key] = sum(
            1 for sid, dt in last_dates.items() if dt >= cutoff)

    one_message = sorted(
        ({"id": sid, "name": names[sid]} for sid, c in counts.items() if c == 1),
        key=lambda u: u["name"].lower(),
    )

    return {
        "cancelled": bool(ctx and ctx.cancelled()),
        "chat_name": chat_name,
        "total_entries": total_in_file,
        "total_authored": counted,
        "total_senders": len(counts),
        "senders_no_date": len(no_date_senders),
        "active_by_period": active_by_period,
        "one_message_users": one_message,
    }


def run_chat_activity(params: dict, ctx) -> str:
    """params: path (chat export .json file). Returns the summary as JSON."""
    summary = analyze_export(params["path"], ctx)
    ctx.log(f"Done: {summary['total_senders']} sender(s), "
            f"{len(summary['one_message_users'])} with exactly one message.")
    return json.dumps(summary)
