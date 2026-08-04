"""Find t.me links posted in a channel that aren't already tracked in an
existing Markdown file (e.g. an export from
https://github.com/Exey/tg-channel-stats), and report each new link's
subscriber count.

Two inputs:
- `md_path`: a local .md file listing known/tracked channels. Its native
  format is a table of `| Folder | Followers | ID/Username |` rows, where
  the last column is either `@username` or a bare numeric channel ID (many
  rows only have the numeric ID, no username) — see `parse_md_known`. Any
  bare t.me/ links elsewhere in the file are picked up too, so a
  differently-formatted MD still works as a "known" source.
- `channel`: a Telegram channel/group to scan for t.me links posted in its
  messages (e.g. a "recommended channels" directory post). A channel can be
  referenced three ways, all detected: a plain "t.me/name" link, a bare
  "@name" mention, or a category label hyperlinked straight to the channel
  (the URL never appears as visible text at all — very common in directory
  posts) — see `_extract_from_text`.

For every link mentioned in the channel but missing from the MD file, the
"tag" is the hyperlink's own visible label when there is one, otherwise the
same line's text before the match, or the previous line if that's empty (the
common "category header, then link" directory format). A link only counts
as "new" if:
- it actually resolves to a real, live @username (broken/typo'd or private
  links are dropped, not just shown with a blank follower count),
- that entity is an actual channel (broadcast or supergroup) — personal
  profiles, bots and plain group chats are filtered out,
- neither its @username nor its resolved numeric ID (channels can be listed
  under either) matches the MD file, and
- its live subscriber count meets `min_followers` (0 = no minimum).
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from .common import resolve_entity, retry

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
                        "proxy", "socks", "c"}


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
        line = raw_line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
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


async def _resolve_link_info(client, ctx, norm_link: str, kind: str) -> dict | None:
    """{'id': int, 'followers': int|None} for a *channel* link specifically —
    None if it's not a resolvable, real channel at all: an invite link (kind
    != 'user'), an unresolvable/private/deleted @username, a personal
    profile, a bot, or a plain group chat (not a broadcast channel /
    supergroup). Followers come from the channel's full info (public data,
    no admin rights needed)."""
    if kind != "user":
        return None  # invite links aren't resolvable to an entity by username
    from telethon.tl.functions.channels import GetFullChannelRequest
    from telethon.tl.types import Channel

    username = norm_link.split("t.me/", 1)[-1]
    try:
        resolved = await retry(ctx, resolve_entity, client, f"@{username}")
        if not isinstance(resolved, Channel):
            return None  # a user/bot profile or a plain group chat, not a channel
        full = await retry(ctx, client, GetFullChannelRequest(resolved))
        if full is None:
            return None
        return {
            "id": resolved.id,
            "followers": getattr(full.full_chat, "participants_count", None),
        }
    except Exception:
        return None


async def compare_links(client, p: dict, ctx) -> str:
    """p: channel, md_path (optional — '' means no known-links filter),
    scan_limit (0 = all), min_followers (0 = no minimum), fetch_followers
    (bool — resolve each candidate for its subscriber count/channel-type/
    numeric-ID check; this is the expensive, flood-prone part), delay
    (seconds to wait between each of those lookups)."""
    md_path = p.get("md_path") or ""
    if md_path:
        known_usernames, known_ids = parse_md_known(md_path)
        ctx.log(f"Loaded {len(known_usernames)} known username(s) and "
                f"{len(known_ids)} known numeric ID(s) from {md_path}")
    else:
        known_usernames, known_ids = set(), set()
        ctx.log("No known-links file given — every channel link found will be reported.")

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

    ctx.log(f"Found {len(found)} unique link(s) in '{title}'.")

    # A link already tracked by @username needs no lookup. Everything else
    # gets resolved — partly for the follower count, partly because it might
    # still be a known channel just listed by numeric ID (or under a since-
    # changed username) in the MD file.
    candidates = {
        norm: info for norm, info in found.items()
        if not (info["kind"] == "user"
                and norm.split("t.me/", 1)[-1] in known_usernames)
    }
    items = sorted(candidates.items())

    fetch_followers = bool(p.get("fetch_followers"))
    if not fetch_followers:
        # Fast path: no per-link API calls at all, so no flood risk — just
        # report what the scan found, unresolved. Numeric-ID matches and the
        # channel-only/min-followers filters need a resolved entity, so they
        # don't apply here.
        ctx.log(f"{len(items)} link(s) not matched by username (follower "
                f"lookup skipped — enable it to verify + get counts).")
        rows = [{"link": norm, "tag": info["tag"], "followers": None}
               for norm, info in items]
        return json.dumps({
            "cancelled": ctx.cancelled(),
            "title": title,
            "known": len(known_usernames) + len(known_ids),
            "scanned_links": len(found),
            "rows": rows,
        })

    delay = float(p.get("delay") or 0)
    ctx.log(f"{len(items)} link(s) not matched by username — checking "
            f"numeric IDs / fetching follower counts "
            f"({delay}s between each to avoid a flood ban)…")

    min_followers = int(p.get("min_followers") or 0)
    rows: list[dict] = []
    skipped_not_channel = 0
    for i, (norm, info) in enumerate(items, 1):
        if ctx.cancelled():
            break
        resolved = await _resolve_link_info(client, ctx, norm, info["kind"])
        if resolved is None:
            skipped_not_channel += 1
        elif resolved["id"] not in known_ids:
            followers = resolved["followers"]
            if followers is not None and followers >= min_followers:
                rows.append({"link": norm, "tag": info["tag"], "followers": followers})
        ctx.progress(i, len(items))
        if delay and i < len(items):
            await asyncio.sleep(delay)

    if skipped_not_channel:
        ctx.log(f"  Skipped {skipped_not_channel} link(s) that aren't a "
                f"resolvable channel (invite link, group, bot, private, …).")

    rows.sort(key=lambda r: r["followers"], reverse=True)

    return json.dumps({
        "cancelled": ctx.cancelled(),
        "title": title,
        "known": len(known_usernames) + len(known_ids),
        "scanned_links": len(found),
        "rows": rows,
    })
