"""Find t.me links posted in a channel and report each one's subscriber
count.

Three separate steps, on purpose — resolving a link's follower count
(`channels.GetFullChannel`) is a method Telegram flood-bans hard if called
too fast, and a single unlucky call can come back with a multi-hour
FloodWait. Doing that inline during a 10k-message scan means one bad request
can strand the whole run. So:

- `scan_channel_links` — the fast, read-only step. Scans every message for
  t.me links and returns them all completely unresolved (no network calls
  beyond the scan itself, so no flood risk regardless of channel size). A
  channel can be referenced three ways in a post, all detected: a plain
  "t.me/name" link, a bare "@name" mention, or a category label hyperlinked
  straight to the channel (the URL never appears as visible text at all —
  very common in "recommended channels" directory posts) — see
  `_extract_from_text`. The "tag" for each link is the hyperlink's own
  visible label when there is one, otherwise the same line's text before
  the match, or the previous line if that's empty.
- `populate_followers` — resolves the scan's `kind: 'user'` rows missing a
  follower count, one at a time (with a delay between each), to get a live
  subscriber count. A row that isn't a real, resolvable channel is kept
  with `broken: True` (❌) rather than retried forever.
- `populate_private_channels` — same idea for `kind: 'invite'` rows
  (t.me/+... links), previewed via `CheckChatInviteRequest` without joining.

Both `populate_*` steps take whatever rows the scan (or a previous, cut-short
populate run) produced, so a flood wait or dropped connection only stops
that step — already-resolved rows are kept, and re-running the same button
picks up only what's left unresolved.

`exclude_by_md` is a separate, on-demand filter — not part of any of the
above — for dropping rows that match a known-links Markdown file (the same
`| Folder | Followers | ID/Username |` format an export from
https://github.com/Exey/tg-channel-stats uses, last column either
`@username` or a bare numeric channel ID; see `parse_md_known`). Call it
whenever, on whatever rows are currently in the table.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from telethon import errors

from .common import resolve_entity

HEARTBEAT_EVERY = 500

# `(?<![\w.])` rejects domains that merely *end* in "t.me" (e.g. "start.me/x"
# would otherwise match "t.me/x" as a substring) by requiring the char right
# before the match to not be alphanumeric/underscore/dot.
LINK_RE = re.compile(r"(?<![\w.])(?:https?://)?t\.me/([A-Za-z0-9_+/-]{1,80})",
                     re.IGNORECASE)
# Bare @mentions (Telegram usernames are 5-32 chars, start with a letter).
# `(?<![\w@])` avoids matching the local part of an email address.
MENTION_RE = re.compile(r"(?<![\w@])@([A-Za-z][A-Za-z0-9_]{3,31})\b")
# A rendered hyperlink where the visible label differs from its target —
# `Message.text` (markdown-rendered) turns a MessageEntityTextUrl into this,
# which is exactly the "category text hyperlinked straight to the channel"
# shape a directory post uses.
MD_LINK_RE = re.compile(r"\[([^\[\]]*)\]\((https?://[^\s)]+)\)")

_SKIP_FIRST_SEGMENTS = {"s", "iv", "share", "addstickers", "addemoji", "addtheme",
                        "proxy", "socks", "c", "boost"}


def _parse_link(raw_path: str) -> tuple[str, str] | None:
    """raw_path is whatever followed 't.me/' in LINK_RE. Returns
    (normalized_link, kind) with kind in {'user', 'invite'}, or None if it's
    not a channel/chat link (preview paths, stickers, private numeric IDs…)."""
    raw_path = raw_path.strip().strip("/")
    if not raw_path:
        return None
    segments = raw_path.split("/")
    first = segments[0]
    low = first.lower()
    if low in _SKIP_FIRST_SEGMENTS:
        return None
    if first.startswith("+"):
        return f"t.me/{first}", "invite"
    if low == "joinchat" and len(segments) > 1:
        return f"t.me/joinchat/{segments[1]}", "invite"
    return f"t.me/{low}", "user"


def _tag_from_context(lines: list[str], line_idx: int, before_text: str) -> str:
    same_line = before_text.strip(" \t-–—•*>")
    if same_line:
        return same_line
    if line_idx > 0:
        return lines[line_idx - 1].strip(" \t-–—•*>")
    return ""


def _extract_from_text(text: str) -> list[tuple[str, str, str]]:
    """[(normalized_link, kind, tag), ...] in order of appearance, combining:
    - rendered hyperlinks `[label](url)` — a directory post's "category text
      linked straight to the channel" shape, where the URL never appears as
      literal text at all;
    - bare `@username` mentions;
    - plain literal t.me/ links.
    `tag` is the hyperlink's own visible label, or (for the other two) the
    same line's text before the match, or the previous line if that's empty.
    """
    if not text:
        return []
    out: list[tuple[str, str, str]] = []

    # 1) [label](url) hyperlinks first, then blank them out (keeping length
    # and newlines intact) so pass 2 doesn't also match the url text inside.
    masked = list(text)
    for m in MD_LINK_RE.finditer(text):
        link_m = LINK_RE.search(m.group(2))
        if link_m:
            parsed = _parse_link(link_m.group(1))
            if parsed:
                norm, kind = parsed
                tag = " ".join(m.group(1).split())
                out.append((norm, kind, tag))
        for i in range(m.start(), m.end()):
            if masked[i] != "\n":
                masked[i] = " "
    masked_text = "".join(masked)
    lines = masked_text.split("\n")

    # 2) Bare @mentions and plain literal t.me/ links in what's left.
    for i, line in enumerate(lines):
        for m in LINK_RE.finditer(line):
            parsed = _parse_link(m.group(1))
            if parsed is None:
                continue
            norm, kind = parsed
            out.append((norm, kind, _tag_from_context(lines, i, line[: m.start()])))
        for m in MENTION_RE.finditer(line):
            norm = f"t.me/{m.group(1).lower()}"
            out.append((norm, "user", _tag_from_context(lines, i, line[: m.start()])))
    return out


def _extract_links_with_tags(msg) -> list[tuple[str, str, str]]:
    """Same as `_extract_from_text`, but prefers the message's markdown-
    rendered `.text` (falls back to the raw `.message`) so links hidden
    behind a hyperlinked label are found too, not just literal "t.me/..."
    text."""
    text = getattr(msg, "text", None)
    if text is None:
        text = getattr(msg, "message", "") or ""
    return _extract_from_text(text)


def _split_md_row(line: str) -> list[str] | None:
    """Split one `| a | b\\| escaped | c |` table line into stripped,
    unescaped cells, or None if it doesn't look like a table row.

    `line[1:-1]` (not `.strip("|")`) deliberately keeps a genuinely empty
    first/last cell — `.strip("|")` would eat the delimiter pipe right along
    with it (e.g. "||t.me/x|tag|" collapsing to "t.me/x|tag" and silently
    losing a whole column) whenever a row's first or last cell is blank.
    """
    line = line.strip()
    if not (line.startswith("|") and line.endswith("|") and len(line) >= 2):
        return None
    inner = line[1:-1]
    cells: list[str] = []
    current: list[str] = []
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch == "\\" and i + 1 < len(inner) and inner[i + 1] == "|":
            current.append("|")
            i += 2
            continue
        if ch == "|":
            cells.append("".join(current).strip())
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    cells.append("".join(current).strip())
    return cells


def parse_md_known(path: str) -> tuple[set[str], set[int]]:
    """Parse the tg-channel-stats table (`| Folder | Followers | ID/Username |`)
    plus any bare t.me/ links anywhere in the file. Returns
    (known_usernames lowercased without '@', known_numeric_ids)."""
    try:
        content = Path(path).read_text(encoding="utf-8")
    except OSError:
        return set(), set()

    usernames: set[str] = set()
    ids: set[int] = set()

    for raw_line in content.splitlines():
        cells = _split_md_row(raw_line)
        if cells is None or len(cells) < 3:
            continue
        last = cells[-1]
        if not last or set(last) <= {"-", ":"} or last.lower() in ("id/username", "id", "username"):
            continue  # header / separator row
        if last.startswith("@"):
            usernames.add(last[1:].lower())
        elif last.lstrip("-").isdigit():
            ids.add(int(last))

    # Also pick up t.me links anywhere, so a differently-formatted MD works too.
    for m in LINK_RE.finditer(content):
        parsed = _parse_link(m.group(1))
        if parsed and parsed[1] == "user":
            usernames.add(parsed[0].split("t.me/", 1)[-1])

    return usernames, ids


def parse_saved_rows(path: str) -> list[dict]:
    """Reads a file previously written by "Save MD" (`|Followers|t.me/
    link|tag|`) back into row dicts, so Populate can resume a run without
    re-scanning the channel from scratch — e.g. after closing the app
    between a flood-wait stop and its cooldown."""
    try:
        content = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []

    rows: list[dict] = []
    for raw_line in content.splitlines():
        cells = _split_md_row(raw_line)
        if cells is None or len(cells) < 3:
            continue
        followers_text, link, tag = cells[0], cells[1], cells[2]
        # A blank Followers cell is a legit "count unknown" row, not a
        # separator — `set("") <= {"-", ":"}` is trivially True (the empty
        # set is a subset of everything), so that check must not fire here.
        if followers_text.lower() == "followers" or (
                followers_text and set(followers_text) <= {"-", ":"}):
            continue  # header / separator row
        if not link.startswith("t.me/"):
            continue
        parsed = _parse_link(link.split("t.me/", 1)[-1])
        if not parsed:
            continue
        norm, kind = parsed
        broken = followers_text == "❌"
        followers = int(followers_text) if followers_text.isdigit() else None
        rows.append({"link": norm, "tag": tag, "kind": kind,
                    "followers": followers, "id": None, "broken": broken})
    return rows


def exclude_by_md(rows: list[dict], md_path: str) -> tuple[list[dict], int]:
    """Drops rows matching a known-links MD (same format as
    `parse_md_known`): by @username always, and by numeric ID for rows
    that have already been through Populate (unresolved rows have no ID
    yet, so they can only be matched by username). Local file read + set
    lookups — no Telegram client needed, safe to call any time on whatever
    rows are currently in the table. Returns (remaining_rows, removed_count)."""
    known_usernames, known_ids = parse_md_known(md_path)
    kept: list[dict] = []
    removed = 0
    for r in rows:
        username = r["link"].split("t.me/", 1)[-1] if r.get("kind") == "user" else None
        rid = r.get("id")
        if (username and username in known_usernames) or (rid is not None and rid in known_ids):
            removed += 1
            continue
        kept.append(r)
    return kept, removed


async def scan_channel_links(client, p: dict, ctx) -> str:
    """p: channel, scan_limit (0 = all). Read-only: no per-link network
    calls, so this is safe to run on any size of channel regardless of
    flood limits."""
    entity = await resolve_entity(client, p["channel"])
    title = str(getattr(entity, "title", p["channel"]))
    scan_limit = int(p.get("scan_limit") or 0)
    try:
        total = (await client.get_messages(entity, limit=0)).total or 0
    except Exception:
        total = 0
    if scan_limit:
        total = min(total, scan_limit) if total else scan_limit
    ctx.log(f"Scanning '{title}' for t.me links…")

    found: dict[str, dict] = {}
    scanned = 0
    async for msg in client.iter_messages(entity, limit=scan_limit or None):
        if ctx.cancelled():
            break
        scanned += 1
        for norm, kind, tag in _extract_links_with_tags(msg):
            if norm not in found:
                found[norm] = {"kind": kind, "tag": tag}
        if scanned % HEARTBEAT_EVERY == 0:
            ctx.log(f"  scanned {scanned}/{total or '?'}…")
        ctx.progress(scanned, total)

    rows = [
        {"link": norm, "tag": info["tag"], "kind": info["kind"],
         "followers": None, "id": None, "broken": False}
        for norm, info in sorted(found.items())
    ]
    ctx.log(f"Found {len(rows)} unique link(s) in '{title}'.")

    return json.dumps({
        "cancelled": ctx.cancelled(),
        "title": title,
        "scanned_links": len(found),
        "rows": rows,
    })


class _FloodStop(Exception):
    """Raised instead of waiting out a FloodWaitError inline — for a batch
    of many per-link lookups, blocking the whole run on one flood wait
    (which can be hours) is worse than stopping now and letting the user
    retry later; already-resolved rows are kept either way."""

    def __init__(self, seconds: int) -> None:
        self.seconds = seconds


def _fmt_seconds(total: int) -> str:
    h, rem = divmod(int(total), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


async def _try_resolve_channel(client, norm_link: str) -> dict:
    """One-shot (no retry/backoff) resolve of a @username link to
    {'status': 'ok', 'id':, 'followers':} or {'status': 'not_channel'} —
    the latter for anything that isn't a real, live broadcast channel or
    supergroup (private/deleted/typo'd username, a personal profile, a bot,
    a plain group chat). Raises _FloodStop / connection errors so the batch
    driver can decide whether to keep going."""
    from telethon.tl.functions.channels import GetFullChannelRequest
    from telethon.tl.types import Channel

    username = norm_link.split("t.me/", 1)[-1]
    try:
        resolved = await resolve_entity(client, f"@{username}")
    except errors.FloodWaitError as e:
        raise _FloodStop(e.seconds) from e
    except (ConnectionError, OSError, asyncio.TimeoutError):
        raise
    except Exception:
        return {"status": "broken"}

    if not isinstance(resolved, Channel):
        return {"status": "broken"}

    try:
        full = await client(GetFullChannelRequest(resolved))
    except errors.FloodWaitError as e:
        raise _FloodStop(e.seconds) from e
    except (ConnectionError, OSError, asyncio.TimeoutError):
        raise
    except Exception:
        return {"status": "broken"}

    return {
        "status": "ok",
        "id": resolved.id,
        "followers": getattr(full.full_chat, "participants_count", None),
    }


async def _try_resolve_invite(client, norm_link: str) -> dict:
    """One-shot preview of an invite link (t.me/+hash or t.me/joinchat/hash)
    via CheckChatInviteRequest — doesn't join. {'status': 'ok', 'id'
    (may be None if not already a member), 'followers', 'title'} or
    {'status': 'not_channel'}."""
    from telethon.tl.functions.messages import CheckChatInviteRequest
    from telethon.tl.types import ChatInvite, ChatInviteAlready, ChatInvitePeek

    tail = norm_link.split("t.me/", 1)[-1]
    if tail.startswith("+"):
        chat_hash = tail[1:]
    elif tail.startswith("joinchat/"):
        chat_hash = tail.split("/", 1)[-1]
    else:
        return {"status": "broken"}

    try:
        result = await client(CheckChatInviteRequest(chat_hash))
    except errors.FloodWaitError as e:
        raise _FloodStop(e.seconds) from e
    except (ConnectionError, OSError, asyncio.TimeoutError):
        raise
    except Exception:
        return {"status": "broken"}

    if isinstance(result, ChatInvite):
        return {"status": "ok", "id": None,
                "followers": result.participants_count, "title": result.title}
    if isinstance(result, (ChatInviteAlready, ChatInvitePeek)):
        chat = result.chat
        return {"status": "ok", "id": getattr(chat, "id", None),
                "followers": getattr(chat, "participants_count", None),
                "title": getattr(chat, "title", None)}
    return {"status": "broken"}


async def _run_resolution_batch(client, ctx, pending: list[dict], delay: float,
                                resolve_one) -> tuple[int, int, int, str | None]:
    """Drives `resolve_one(client, row) -> dict` over `pending`, mutating
    each row in place based on the returned status:
    - 'ok' (+ fields to merge in) — resolved successfully.
    - 'excluded' — a real channel, but filtered out for an unrelated reason
      (already known by numeric ID, below the follower minimum) — silently
      dropped from the row list, same as if it were never found.
    - 'broken' — confirmed *not* a resolvable channel/invite at all
      (private, deleted, typo'd, a personal profile, a bot, a plain group).
      Kept in the row list with `row['broken'] = True` so the link isn't
      retried forever and shows up as ❌ rather than silently vanishing.
    `resolve_one` may also raise _FloodStop or a connection error.

    A flood wait or an unrecoverable connection loss stops the *whole*
    batch rather than just skipping that one row — grinding through the
    rest one-by-one right after either is pointless (still flood-limited)
    or impossible (still disconnected). Returns
    (resolved_count, excluded_count, broken_count, stopped_reason)."""
    resolved = excluded = broken = 0
    reconnects = 0
    stopped_reason: str | None = None

    for i, row in enumerate(pending, 1):
        if ctx.cancelled():
            break
        try:
            info = await resolve_one(client, row)
        except _FloodStop as e:
            stopped_reason = (f"Telegram's flood limit kicked in — wait "
                              f"~{_fmt_seconds(e.seconds)} before running this "
                              f"again (already-resolved links are kept).")
            break
        except (ConnectionError, OSError, asyncio.TimeoutError) as e:
            if reconnects >= 3:
                stopped_reason = "Lost connection to Telegram repeatedly — stopping for now."
                break
            reconnects += 1
            ctx.log(f"  Connection issue ({e}) — reconnecting ({reconnects}/3)…")
            try:
                if not client.is_connected():
                    await client.connect()
                info = (await resolve_one(client, row)
                       if client.is_connected() else None)
            except _FloodStop as e2:
                stopped_reason = (f"Telegram's flood limit kicked in — wait "
                                  f"~{_fmt_seconds(e2.seconds)} before running "
                                  f"this again (already-resolved links are kept).")
                break
            except Exception:
                info = None
            if info is None:
                stopped_reason = "Lost connection to Telegram and couldn't reconnect — stopping for now."
                break

        status = info.get("status")
        if status == "ok":
            row.update({k: v for k, v in info.items() if k != "status"})
            resolved += 1
        elif status == "excluded":
            row["_drop"] = True
            excluded += 1
        else:  # 'broken'
            row["broken"] = True
            broken += 1
        ctx.progress(i, len(pending))
        if delay and i < len(pending):
            await asyncio.sleep(delay)

    return resolved, excluded, broken, stopped_reason


async def populate_followers(client, p: dict, ctx) -> str:
    """p: rows (from scan_channel_links / a previous populate_* run),
    min_followers (0 = no minimum), delay (seconds between each lookup).
    Resolves 'user'-kind rows missing a follower count and not already
    marked broken — i.e. it always starts from whatever's still empty, so
    rows already resolved (by an earlier run, or loaded from a saved MD)
    are left untouched. A row that resolves to a real channel but falls
    below min_followers is silently dropped; one that isn't a resolvable
    channel at all is kept with `broken: True` (shows as ❌) so it isn't
    retried forever."""
    rows = list(p.get("rows") or [])
    min_followers = int(p.get("min_followers") or 0)
    delay = float(p.get("delay") or 2.0)

    pending = [r for r in rows if r.get("kind") == "user"
              and r.get("followers") is None and not r.get("broken")]
    if not pending:
        ctx.log("Nothing to resolve — every username link is either done or marked broken.")
    else:
        ctx.log(f"Resolving {len(pending)} username link(s), {delay}s apart…")

    async def resolve_one(client, row):
        info = await _try_resolve_channel(client, row["link"])
        if info["status"] != "ok":
            return info  # 'broken' — not a resolvable channel at all
        if info["followers"] is None or info["followers"] < min_followers:
            return {"status": "excluded"}
        return {"status": "ok", "id": info["id"], "followers": info["followers"]}

    resolved, excluded, broken, stopped_reason = await _run_resolution_batch(
        client, ctx, pending, delay, resolve_one)
    rows = [r for r in rows if not r.get("_drop")]

    if stopped_reason:
        ctx.log(f"  Stopped early: {stopped_reason}")
    ctx.log(f"Resolved {resolved} link(s); excluded {excluded} (below the "
            f"follower minimum); marked {broken} broken (❌ — not a "
            f"resolvable channel).")

    return json.dumps({
        "cancelled": ctx.cancelled(),
        "rows": rows,
        "resolved": resolved,
        "dropped": excluded + broken,
        "stopped_reason": stopped_reason,
    })


async def populate_private_channels(client, p: dict, ctx) -> str:
    """Same as populate_followers, but for 'invite'-kind rows (t.me/+... /
    t.me/joinchat/... links), previewed without joining."""
    rows = list(p.get("rows") or [])
    min_followers = int(p.get("min_followers") or 0)
    delay = float(p.get("delay") or 2.0)

    pending = [r for r in rows if r.get("kind") == "invite"
              and r.get("followers") is None and not r.get("broken")]
    if not pending:
        ctx.log("Nothing to resolve — every invite link is either done or marked broken.")
    else:
        ctx.log(f"Checking {len(pending)} invite link(s), {delay}s apart…")

    async def resolve_one(client, row):
        info = await _try_resolve_invite(client, row["link"])
        if info["status"] != "ok":
            return info  # 'broken' — invalid/expired invite
        if info["followers"] is not None and info["followers"] < min_followers:
            return {"status": "excluded"}
        if not row.get("tag") and info.get("title"):
            row["tag"] = info["title"]
        return {"status": "ok", "id": info["id"], "followers": info["followers"]}

    resolved, excluded, broken, stopped_reason = await _run_resolution_batch(
        client, ctx, pending, delay, resolve_one)
    rows = [r for r in rows if not r.get("_drop")]

    if stopped_reason:
        ctx.log(f"  Stopped early: {stopped_reason}")
    ctx.log(f"Resolved {resolved} invite link(s); excluded {excluded}; "
            f"marked {broken} broken (❌ — invalid/expired invite).")

    return json.dumps({
        "cancelled": ctx.cancelled(),
        "rows": rows,
        "resolved": resolved,
        "dropped": excluded + broken,
        "stopped_reason": stopped_reason,
    })
