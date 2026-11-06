#!/usr/bin/env python3
"""
Instagram Repurpose — the side channels for @threelittlereaders: Stories (for
followers: outtakes, reel reshares, question boxes) and Threads (for strangers
who read: a free test bench for hooks before spending footage on them).
SOP: directives/threelittlereaders/00_pipeline.md (Repurpose) + roles/copywriter.md.

Every post file has a Repurpose section the Copywriter fills in the same pass.
When something goes out, it's logged here (one line, no model needed):

  story     log that a Story went up (default today), optionally what it was.
            The frequency-test review reads these dates, so post Stories freely
            and the 22 Oct decision will show whether they were evenly spread.
  threads   log a Threads post: --text "…" --kind hook-test|caption-cut|other
  result    add numbers later: --id RP-004 --views 900 --replies 12 --reposts 3
  list      what's gone out (--channel story|threads, --days N)
  wins      Threads hook tests ranked by replies per 1k views: candidates for
            reel hooks and evidence for execution/instagram_hooks.py

Story question-box answers aren't logged here: they're the audience's own words,
so they go through instagram_signals.py add (source: "our story RP-…").

Usage:
    python3 execution/instagram_repurpose.py story --post IG-021 --text "Meanwhile, on backing vocals…"
    python3 execution/instagram_repurpose.py threads --post IG-021 --kind hook-test --text "Turns out our Nutribullet is a letterbox now."
    python3 execution/instagram_repurpose.py result --id RP-002 --views 640 --replies 9
    python3 execution/instagram_repurpose.py wins
"""

import argparse
import csv
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parent.parent / "outputs" / "instagram" / "repurpose_log.csv"
FIELDS = ["id", "date", "channel", "post", "kind", "text", "views", "replies", "reposts", "likes", "notes"]
KINDS = {"story": ["outtake", "reshare", "question", "poll", "other"],
         "threads": ["hook-test", "caption-cut", "conversation", "other"]}


class RepurposeError(Exception):
    pass


def load():
    if not LOG_FILE.exists():
        return []
    with LOG_FILE.open(newline="") as f:
        return list(csv.DictReader(f))


def save(rows):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date() if s else date.today()


def story_days(start, end):
    """Dates in [start, end] with at least one Story logged (read by the frequency test)."""
    out = set()
    for r in load():
        if r["channel"] == "story":
            d = parse_date(r["date"])
            if start <= d <= end:
                out.add(d)
    return out


def add(channel, a):
    rows = load()
    n = max((int(r["id"][3:]) for r in rows if r["id"].startswith("RP-")), default=0) + 1
    kind = a.kind or ("outtake" if channel == "story" else "hook-test")
    if kind not in KINDS[channel]:
        raise RepurposeError(f"kind '{kind}' for {channel}: use {', '.join(KINDS[channel])}")
    if channel == "threads" and not a.text:
        raise RepurposeError("Threads posts need --text (it's what gets tested).")
    if channel == "threads" and len(a.text) > 500:
        raise RepurposeError(f"{len(a.text)} characters: Threads allows 500.")
    row = {f: "" for f in FIELDS}
    row.update(id=f"RP-{n:03d}", date=parse_date(a.date).isoformat(), channel=channel,
               post=(a.post or "").upper(), kind=kind, text=a.text or "", notes=a.notes or "")
    rows.append(row)
    save(rows)
    return [f"{row['id']} · {row['date']} · {channel} · {kind}" + (f" · {row['post']}" if row["post"] else "")
            + (f"\n  {row['text']}" if row["text"] else "")]


def cmd_result(a):
    rows = load()
    r = next((r for r in rows if r["id"].upper() == a.id.upper()), None)
    if not r:
        raise RepurposeError(f"No {a.id} in the log.")
    for k in ("views", "replies", "reposts", "likes"):
        if getattr(a, k) is not None:
            r[k] = str(getattr(a, k))
    if a.notes:
        r["notes"] = "; ".join(x for x in (r["notes"], a.notes) if x)
    save(rows)
    return [f"{r['id']} updated: views {r['views'] or '–'} · replies {r['replies'] or '–'} · reposts {r['reposts'] or '–'}"]


def cmd_list(a):
    rows = load()
    if a.channel:
        rows = [r for r in rows if r["channel"] == a.channel]
    if a.days:
        cutoff = date.today() - timedelta(days=a.days)
        rows = [r for r in rows if parse_date(r["date"]) >= cutoff]
    return [f"{r['id']} · {r['date']} · {r['channel']} · {r['kind']}" + (f" · {r['post']}" if r["post"] else "")
            + (f"\n  {r['text']}" if r["text"] else "") for r in rows] or ["Nothing logged yet."]


def per_k(r):
    try:
        return int(r["replies"]) / int(r["views"]) * 1000
    except (ValueError, ZeroDivisionError):
        return None


def cmd_wins(a):
    tests = [r for r in load() if r["channel"] == "threads" and r["kind"] == "hook-test"]
    scored = sorted((r for r in tests if per_k(r) is not None), key=per_k, reverse=True)
    pending = [r for r in tests if per_k(r) is None]
    out = ["Threads hook tests, by replies per 1k views (a signal to try it on a reel, not proof: Threads readers aren't Sally)"]
    out += [f"  {per_k(r):5.1f}/1k · {r['replies']} replies · {r['views']} views · {r['id']} ({r['post'] or '–'})\n"
            f"         {r['text']}" for r in scored] or ["  (no results logged yet)"]
    if pending:
        out.append(f"\n{len(pending)} test(s) waiting for numbers: " + ", ".join(r["id"] for r in pending))
    return out


def main():
    ap = argparse.ArgumentParser(description="Log Stories and Threads posts for @threelittlereaders.")
    sub = ap.add_subparsers(dest="command", required=True)
    for ch in ("story", "threads"):
        p = sub.add_parser(ch)
        p.add_argument("--text")
        p.add_argument("--post", help="The IG-0xx it came from")
        p.add_argument("--kind", help=", ".join(KINDS[ch]))
        p.add_argument("--date", help="YYYY-MM-DD (default: today)")
        p.add_argument("--notes")
    p = sub.add_parser("result")
    p.add_argument("--id", required=True)
    for k in ("views", "replies", "reposts", "likes"):
        p.add_argument(f"--{k}", type=int)
    p.add_argument("--notes")
    p = sub.add_parser("list")
    p.add_argument("--channel", choices=["story", "threads"])
    p.add_argument("--days", type=int)
    sub.add_parser("wins")
    a = ap.parse_args()
    try:
        if a.command in ("story", "threads"):
            out = add(a.command, a)
        else:
            out = {"result": cmd_result, "list": cmd_list, "wins": cmd_wins}[a.command](a)
    except RepurposeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print("\n".join(out))


if __name__ == "__main__":
    main()
