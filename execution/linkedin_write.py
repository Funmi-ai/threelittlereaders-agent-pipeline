#!/usr/bin/env python3
"""
LinkedIn Write — the only way data gets into the LinkedIn Post Tracker
(built by linkedin_tracker.py). Execution layer for directives/linkedin_experiment.md.

The user talks in chat ("logged the gym post, link is ...", "that post got
4,200 impressions, 90 reactions, 12 comments"); Claude Code maps that to one
of these calls. There is no API for personal-profile post insights, so every
number comes from LinkedIn's own "View analytics" screen on the post, by hand.

Subcommands:
  log       add a new post (one row, ID auto-assigned): --track --topic
            [--date, defaults today] [--link] [--impressions ... in one go]
  insights  update metrics for an existing post (re-running overwrites the
            numbers with the newer capture — the post's analytics firm up
            over the first few days)
  report    posts logged, average engagement rate, best/worst, by track

Usage:
    python3 execution/linkedin_write.py log --track Personal --topic "Gym post — disservice" --link https://...
    python3 execution/linkedin_write.py insights --id LI-001 --impressions 4200 --reactions 90 --comments 12 --reposts 3
    python3 execution/linkedin_write.py report
"""

import argparse
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

from linkedin_tracker import (DEFAULT_OUTPUT, METRICS, POSTS_COLS, POSTS_LAST_ROW, SchemaError,
                              TRACKS, check_schema)

BACKUP_DIR = Path(__file__).resolve().parent.parent / "outputs" / "linkedin" / "backups"
MAX_BACKUPS = 50


class TrackerError(Exception):
    pass


def check_lock_file(path: Path):
    lock = path.parent / f"~${path.name}"
    if lock.exists():
        print(
            f"⚠  {lock.name} found next to the tracker — it looks like the file is open "
            "in Excel/Numbers. If it gets saved from there after this runs, these changes "
            "will be overwritten.",
            file=sys.stderr,
        )


def backup(path: Path):
    if not path.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, BACKUP_DIR / f"{stamp}_{path.name}")
    existing = sorted(BACKUP_DIR.glob(f"*_{path.name}"))
    for old in existing[:-MAX_BACKUPS]:
        old.unlink()


def parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise TrackerError(f"Date '{s}' must be in YYYY-MM-DD format.")


def choose(value, choices, field):
    if value is None:
        return None
    for c in choices:
        if c.lower() == value.lower():
            return c
    raise TrackerError(f"{field} must be one of: {', '.join(choices)} (got '{value}').")


def first_blank(ws, last, col=1, start=2):
    for r in range(start, last + 1):
        if ws.cell(row=r, column=col).value in (None, ""):
            return r
    raise TrackerError(f"No blank rows left on '{ws.title}' (up to row {last}).")


def next_id(ws):
    nums = []
    for r in range(2, POSTS_LAST_ROW + 1):
        pid = str(ws.cell(row=r, column=POSTS_COLS["id"]).value or "")
        if pid.startswith("LI-") and pid[3:].isdigit():
            nums.append(int(pid[3:]))
    return f"LI-{(max(nums) if nums else 0) + 1:03d}"


def find_post(ws, pid):
    pid = pid.strip().upper()
    for r in range(2, POSTS_LAST_ROW + 1):
        if str(ws.cell(row=r, column=POSTS_COLS["id"]).value or "").upper() == pid:
            return r
    raise TrackerError(f"No post with ID {pid} in Posts.")


def cmd_log(wb, a):
    ws = wb["Posts"]
    track = choose(a.track, TRACKS, "Track") or "Other"
    when = parse_date(a.date) if a.date else date.today()
    r = first_blank(ws, POSTS_LAST_ROW)
    pid = next_id(ws)
    ws.cell(row=r, column=POSTS_COLS["id"], value=pid)
    ws.cell(row=r, column=POSTS_COLS["posted_date"], value=when)
    ws.cell(row=r, column=POSTS_COLS["track"], value=track)
    ws.cell(row=r, column=POSTS_COLS["topic"], value=a.topic)
    if a.link:
        ws.cell(row=r, column=POSTS_COLS["link"], value=a.link)
    if a.notes:
        ws.cell(row=r, column=POSTS_COLS["notes"], value=a.notes)
    metrics = {m: getattr(a, m) for m in METRICS if getattr(a, m) is not None}
    for m, v in metrics.items():
        ws.cell(row=r, column=POSTS_COLS[m], value=v)
    out = [f"Logged {pid} ({track}): {a.topic} — {when.isoformat()}"]
    if metrics:
        out.append("    " + " · ".join(f"{k} {v:,}" for k, v in metrics.items()))
    return True, out


def cmd_insights(wb, a):
    ws = wb["Posts"]
    r = find_post(ws, a.id)
    metrics = {m: getattr(a, m) for m in METRICS if getattr(a, m) is not None}
    if not metrics:
        raise TrackerError("Give at least one metric (e.g. --impressions 4200 --reactions 90).")
    for m, v in metrics.items():
        if v < 0:
            raise TrackerError(f"{m} can't be negative.")
    for m, v in metrics.items():
        ws.cell(row=r, column=POSTS_COLS[m], value=v)
    if a.notes:
        ws.cell(row=r, column=POSTS_COLS["notes"], value=a.notes)

    pid = ws.cell(row=r, column=POSTS_COLS["id"]).value
    topic = ws.cell(row=r, column=POSTS_COLS["topic"]).value
    impressions = ws.cell(row=r, column=POSTS_COLS["impressions"]).value
    out = [f"Updated insights for {pid} ({topic}):",
           "    " + " · ".join(f"{k} {v:,}" for k, v in metrics.items())]
    if impressions:
        n = lambda k: ws.cell(row=r, column=POSTS_COLS[k]).value or 0
        er = (n("reactions") + n("comments") + n("reposts")) / impressions
        out.append(f"    engagement rate {er:.1%}")
    else:
        out.append("    (no impressions yet — engagement rate needs that first)")
    return True, out


def cmd_report(wb, a):
    ws = wb["Posts"]
    posts = []
    for r in range(2, POSTS_LAST_ROW + 1):
        pid = ws.cell(row=r, column=POSTS_COLS["id"]).value
        if not pid:
            continue
        impr = ws.cell(row=r, column=POSTS_COLS["impressions"]).value
        rxn = ws.cell(row=r, column=POSTS_COLS["reactions"]).value or 0
        cmt = ws.cell(row=r, column=POSTS_COLS["comments"]).value or 0
        rpt = ws.cell(row=r, column=POSTS_COLS["reposts"]).value or 0
        er = (rxn + cmt + rpt) / impr if impr else None
        posts.append({"id": pid, "date": ws.cell(row=r, column=POSTS_COLS["posted_date"]).value,
                      "track": ws.cell(row=r, column=POSTS_COLS["track"]).value,
                      "topic": ws.cell(row=r, column=POSTS_COLS["topic"]).value,
                      "impressions": impr, "er": er})
    if not posts:
        return False, ["No posts logged yet. `log` one first."]

    out = [f"{len(posts)} post(s) logged."]
    rated = [p for p in posts if p["er"] is not None]
    if rated:
        avg = sum(p["er"] for p in rated) / len(rated)
        out.append(f"Average engagement rate: {avg:.1%} (across {len(rated)} with impressions logged)")
        best = max(rated, key=lambda p: p["er"])
        worst = min(rated, key=lambda p: p["er"])
        out.append(f"Best: {best['id']} — {best['topic']} ({best['er']:.1%})")
        out.append(f"Weakest: {worst['id']} — {worst['topic']} ({worst['er']:.1%})")
    else:
        out.append("No impressions logged yet, so no engagement rates to compare.")
    by_track = {}
    for p in posts:
        by_track.setdefault(p["track"] or "Other", 0)
        by_track[p["track"] or "Other"] += 1
    out.append("By track: " + " · ".join(f"{k} {v}" for k, v in by_track.items()))
    return False, out


def build_parser():
    ap = argparse.ArgumentParser(description="Write to the LinkedIn Post Tracker.")
    ap.add_argument("--file", default=str(DEFAULT_OUTPUT), help="Path to the tracker workbook.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    log = sub.add_parser("log", help="Add a new post.")
    log.add_argument("--track", choices=TRACKS)
    log.add_argument("--topic", required=True)
    log.add_argument("--date", help="YYYY-MM-DD, defaults to today.")
    log.add_argument("--link")
    log.add_argument("--notes")
    for m in METRICS:
        log.add_argument(f"--{m}", type=int)

    ins = sub.add_parser("insights", help="Update metrics for an existing post.")
    ins.add_argument("--id", required=True)
    ins.add_argument("--notes")
    for m in METRICS:
        ins.add_argument(f"--{m}", type=int)

    sub.add_parser("report", help="Summary: posts logged, engagement, best/worst, by track.")
    return ap


def main():
    args = build_parser().parse_args()
    path = Path(args.file)
    if not path.exists():
        print(f"{path} doesn't exist yet. Run: python3 execution/linkedin_tracker.py")
        sys.exit(1)
    check_lock_file(path)
    wb = load_workbook(path)
    try:
        check_schema(wb)
        fn = {"log": cmd_log, "insights": cmd_insights, "report": cmd_report}[args.cmd]
        changed, lines = fn(wb, args)
    except (TrackerError, SchemaError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    if changed:
        backup(path)
        wb.save(path)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
