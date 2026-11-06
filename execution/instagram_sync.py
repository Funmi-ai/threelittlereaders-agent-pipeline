#!/usr/bin/env python3
"""
Instagram Sync — pulls post insights and follower count from the Instagram
API (Instagram Login flavour, graph.instagram.com) into the tracker built by
instagram_tracker.py. Part of directives/instagram_content.md.

What it does on each run:
  1. Refreshes the long-lived token if it's more than REFRESH_AFTER_DAYS old
     (tokens expire after 60 days; refreshing resets the clock) and writes the
     new one back to .env.
  2. Logs today's follower count (once per day).
  3. For every feed post/reel: matches it to a Content Plan row (by link, then
     by posted date), or adds a new Posted row for posts that were never in
     the plan, then writes its metrics to Insights.

What the API doesn't give (per Meta's media insights reference): follows and
non-follower % for any post, profile visits for reels. Those stay as logged
from screenshots — upsert_insights only overwrites the metrics passed in.

Needs in .env:
    INSTAGRAM_ACCESS_TOKEN=...      (from App Dashboard → Instagram → API setup
                                     with Instagram business login → Generate token)
    INSTAGRAM_TOKEN_REFRESHED=YYYY-MM-DD   (written by this script)

Usage:
    python3 execution/instagram_sync.py              # sync everything
    python3 execution/instagram_sync.py --limit 10   # most recent 10 posts only
    python3 execution/instagram_sync.py --dry-run    # fetch and print, write nothing
"""

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from openpyxl import load_workbook

from zoneinfo import ZoneInfo

from instagram_tracker import (DEFAULT_OUTPUT, EVENING_FROM_HOUR, FOLLOWERS_LAST_ROW, PLAN_COLS,
                               PLAN_LAST_ROW, SchemaError, check_schema)

UK = ZoneInfo("Europe/London")


def uk_time(media):
    return datetime.strptime(media["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(UK)


def slot_of(media):
    return "Evening" if uk_time(media).hour >= EVENING_FROM_HOUR else "Lunch"
from instagram_write import (
    TrackerError,
    backup,
    check_lock_file,
    first_blank,
    next_id,
    plan_rows,
    upsert_insights,
)

API = "https://graph.instagram.com/v23.0"
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
REFRESH_AFTER_DAYS = 7

# Requested per media type. API name → tracker metric.
REEL_METRICS = {"reach": "reach", "views": "views", "likes": "likes", "comments": "comments",
                "shares": "shares", "saved": "saves", "ig_reels_avg_watch_time": "watch_time",
                "reels_skip_rate": "skip_rate"}
FEED_METRICS = {"reach": "reach", "views": "views", "likes": "likes", "comments": "comments",
                "shares": "shares", "saved": "saves", "profile_visits": "profile_visits"}
FORMAT_FOR = {"REELS": "Reel", "CAROUSEL_ALBUM": "Carousel", "IMAGE": "Photo", "VIDEO": "Reel"}


# --------------------------------------------------------------------------
# .env handling — read/update single keys without disturbing other lines
# --------------------------------------------------------------------------
def read_env(key):
    if not ENV_PATH.exists():
        return None
    for line in ENV_PATH.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def write_env(key, value):
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
def api_get(path, token, **params):
    url = path if path.startswith("http") else f"{API}/{path}"
    if not path.startswith("http"):
        params["access_token"] = token
    resp = requests.get(url, params=params, timeout=30)
    data = resp.json()
    if "error" in data:
        err = data["error"]
        raise TrackerError(f"Instagram API: {err.get('message')} (code {err.get('code')})")
    return data


def maybe_refresh_token(token):
    """Long-lived tokens can be refreshed once they're 24h+ old; doing it
    weekly keeps the 60-day expiry from ever arriving. Failure isn't fatal —
    the current token keeps working until it actually expires."""
    last = read_env("INSTAGRAM_TOKEN_REFRESHED")
    if last:
        try:
            if date.today() - datetime.strptime(last, "%Y-%m-%d").date() < timedelta(days=REFRESH_AFTER_DAYS):
                return token, None
        except ValueError:
            pass
    try:
        data = api_get("https://graph.instagram.com/refresh_access_token", None,
                       grant_type="ig_refresh_token", access_token=token)
    except TrackerError as e:
        if not last:
            # Brand-new token (<24h old) can't be refreshed yet; start the clock.
            write_env("INSTAGRAM_TOKEN_REFRESHED", date.today().isoformat())
            return token, None
        return token, f"⚠  Token refresh failed ({e}). It still works until it expires — check soon."
    write_env("INSTAGRAM_ACCESS_TOKEN", data["access_token"])
    write_env("INSTAGRAM_TOKEN_REFRESHED", date.today().isoformat())
    return data["access_token"], f"Token refreshed (valid ~{data.get('expires_in', 0) // 86400} days)."


def fetch_media(token, limit):
    fields = "id,caption,media_type,media_product_type,permalink,timestamp"
    data = api_get("me/media", token, fields=fields, limit=min(limit or 50, 50))
    items = list(data.get("data", []))
    while data.get("paging", {}).get("next") and (not limit or len(items) < limit):
        data = api_get(data["paging"]["next"], token)
        items.extend(data.get("data", []))
    return items[:limit] if limit else items


def metric_value(entry):
    if "total_value" in entry:
        return entry["total_value"].get("value")
    values = entry.get("values") or [{}]
    return values[0].get("value")


def fetch_insights(media, token):
    """Ask for all metrics in one call; if Meta rejects one (metrics vary by
    media type and change over time), fall back to one call per metric and
    skip the ones it won't give."""
    wanted = REEL_METRICS if media.get("media_product_type") == "REELS" else FEED_METRICS
    try:
        rows = api_get(f"{media['id']}/insights", token, metric=",".join(wanted))["data"]
    except TrackerError:
        rows = []
        for name in wanted:
            try:
                rows += api_get(f"{media['id']}/insights", token, metric=name)["data"]
            except TrackerError:
                continue
    out = {}
    for entry in rows:
        key = wanted.get(entry.get("name"))
        v = metric_value(entry)
        if key is None or v is None:
            continue
        if key == "watch_time":
            v = round(v / 1000, 1)          # API gives milliseconds
        elif key == "skip_rate":
            v = v / 100 if v > 1 else v     # stored as a fraction like the sheet's other % columns
        out[key] = v
    return out


# --------------------------------------------------------------------------
# Matching API posts to the Content Plan
# --------------------------------------------------------------------------
def shortcode(url):
    # Share links carry ?igsh=… tracking; the shortcode is the last path part.
    parts = [p for p in str(url or "").split("?")[0].split("/") if p]
    return parts[-1] if parts else None


def caption_title(caption):
    first = (caption or "").strip().splitlines()[0] if (caption or "").strip() else "(no caption)"
    return first if len(first) <= 120 else first[:117] + "…"


def match_or_create(wb, media, posted):
    """Return (plan_row, record, how). Matching order: same link → a single
    unlinked plan row dated (or posted) that day in the same slot (lunch /
    evening, from the UK posting time) → new row."""
    slot = slot_of(media)
    ws = wb["Content Plan"]
    code = shortcode(media.get("permalink"))
    rows = list(plan_rows(ws))
    for r, rec in rows:
        if code and shortcode(rec["link"]) == code:
            return r, rec, "matched"
    same_day = [(r, rec) for r, rec in rows if not rec["link"] and rec["status"] != "Skipped"
                and posted in (rec["posted_date"], rec["date"]) and (rec.get("slot") or slot) == slot]
    if len(same_day) == 1:
        r, rec = same_day[0]
        ws.cell(row=r, column=PLAN_COLS["link"], value=media.get("permalink"))
        if not rec["format"]:
            rec["format"] = FORMAT_FOR.get(media.get("media_product_type")) or FORMAT_FOR.get(media.get("media_type"))
            ws.cell(row=r, column=PLAN_COLS["format"], value=rec["format"])
        rec["link"] = media.get("permalink")
        if not rec.get("slot"):
            ws.cell(row=r, column=PLAN_COLS["slot"], value=slot)
        return r, rec, "linked"

    r = first_blank(ws, PLAN_LAST_ROW, col=PLAN_COLS["idea"])
    fmt = FORMAT_FOR.get(media.get("media_product_type")) or FORMAT_FOR.get(media.get("media_type"))
    rec = {"id": next_id(ws), "date": posted, "slot": slot, "idea": caption_title(media.get("caption")), "format": fmt,
           "pillar": None, "angle": None, "hook": None, "caption": None, "status": "Posted", "posted_date": posted,
           "link": media.get("permalink"), "notes": "Added by Instagram sync — needs a pillar"}
    for k, v in rec.items():
        if v is not None:
            ws.cell(row=r, column=PLAN_COLS[k], value=v)
    return r, rec, "new"


def log_followers(wb, count):
    ws = wb["Followers"]
    today = date.today()
    for r in range(2, FOLLOWERS_LAST_ROW + 1):
        d = ws.cell(row=r, column=1).value
        if isinstance(d, datetime) and d.date() == today:
            ws.cell(row=r, column=2, value=count)
            return f"Followers today: {count:,} (updated today's entry)"
    r = first_blank(ws, FOLLOWERS_LAST_ROW, col=2)
    prev = ws.cell(row=r - 1, column=2).value if r > 2 else None
    ws.cell(row=r, column=1, value=today)
    ws.cell(row=r, column=2, value=count)
    ws.cell(row=r, column=4, value="Instagram sync")
    change = f" ({count - prev:+,} since last entry)" if isinstance(prev, (int, float)) else ""
    return f"Followers today: {count:,}{change}"


# --------------------------------------------------------------------------
def run(args):
    token = read_env("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        raise TrackerError("No INSTAGRAM_ACCESS_TOKEN in .env — see the setup steps in directives/instagram_content.md.")
    path = Path(args.file).expanduser()
    if not path.exists():
        raise TrackerError(f"Tracker not found at {path}.")

    out = []
    if not args.dry_run:
        token, note = maybe_refresh_token(token)
        if note:
            out.append(note)

    me = api_get("me", token, fields="username,followers_count,media_count")
    out.append(f"@{me.get('username')} · {me.get('followers_count', 0):,} followers · {me.get('media_count', 0)} posts")
    media = fetch_media(token, args.limit)
    if not args.dry_run:  # live captions, so post-file checks catch reuse of posts that never had a draft (27 Oct)
        import json
        (Path(path).parent / "live_captions.json").write_text(json.dumps(
            [{"date": str(uk_time(m).date()), "link": m.get("permalink"), "caption": m.get("caption") or ""} for m in media],
            ensure_ascii=False, indent=1))

    wb = load_workbook(path)
    check_schema(wb)
    if not args.dry_run and me.get("followers_count") is not None:
        out.append(log_followers(wb, me["followers_count"]))

    new_posts, synced = [], 0
    for m in media:
        posted = uk_time(m).date()  # UK date, so a late-night post lands on the right day
        metrics = fetch_insights(m, token)
        if args.dry_run:
            out.append(f"  {posted} · {m.get('media_product_type')} · {caption_title(m.get('caption'))[:50]} · {metrics}")
            continue
        r, rec, how = match_or_create(wb, m, posted)
        upsert_insights(wb, r, rec, metrics, date.today(), posted)
        synced += 1
        if how == "new":
            new_posts.append(f"  {rec['id']} · {posted:%a %-d %b} · {rec['format']} · {rec['idea']}")

    if args.dry_run:
        return out + ["(dry run — nothing written)"]

    check_lock_file(path)
    backup(path)
    wb.save(path)
    out.append(f"Synced {synced} post(s).")
    if new_posts:
        out += [f"{len(new_posts)} post(s) weren't in the plan and were added (need a pillar):"] + new_posts
    out.append("Still from screenshots: follows, non-follower %, and profile visits on reels.")
    return out


def main():
    ap = argparse.ArgumentParser(description="Sync Instagram insights into the tracker.")
    ap.add_argument("--file", default=str(DEFAULT_OUTPUT))
    ap.add_argument("--limit", type=int, help="Only the N most recent posts")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        out = run(args)
    except (TrackerError, SchemaError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except requests.RequestException as e:
        print(f"Error: couldn't reach Instagram ({e})", file=sys.stderr)
        sys.exit(1)
    print("\n".join(out))


if __name__ == "__main__":
    main()
