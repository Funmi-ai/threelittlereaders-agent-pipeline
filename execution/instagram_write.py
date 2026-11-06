#!/usr/bin/env python3
"""
Instagram Write — the only way data gets into the Instagram tracker
(built by instagram_tracker.py). Execution layer for directives/instagram_content.md.

The user talks in chat ("new idea: ...", "what's today's post?", "the reel got
1,200 views and 40 saves"); Claude Code maps that to one of these calls.

Subcommands:
  idea       add an idea; auto-scheduled to the next free posting day
             (from Settings) unless --date is given or --unscheduled is set
  schedule   give a date + ID to any ideas typed straight into the sheet
             (--include-bank also dates ideas banked with --unscheduled)
  today      show the post planned for today (or --date), plus anything missed
  upcoming   show the next N days of the plan (default 7)
  move       reschedule a post: --id IG-004 --date 2026-10-09
  edit       change a post's idea/format/pillar/hook/caption/notes/link
  status     set a post's status: --id IG-004 --status Drafted
  pipeline   every open post grouped by stage, with whose move it is next
             (directives/threelittlereaders/00_pipeline.md)
  posted     mark a post as posted (date defaults to today, optional --link)
  insights   log or update metrics for a post (one row per post; re-running
             for the same ID overwrites the numbers with the newer capture)
  followers  log today's follower count
  report     top posts and averages by format/pillar, printed for chat
  patterns   structural correlations (question vs statement covers, length,
             direct address, specificity) against skip rate and follows/1k —
             run before writing new hook/cover options, not just after a flop
  review     the Sunday loop: goal pace, screenshots needed, verdicts to
             confirm, winners to remix, next 7 days' tests
  settings   show or change posting days (--days Mon,Wed,Fri) and pillars

Usage:
    python3 execution/instagram_write.py idea --idea "5yo spells granular" --format Reel --pillar PROVE --angle RELATE
    python3 execution/instagram_write.py today
    python3 execution/instagram_write.py posted --id IG-001 --link https://instagram.com/p/xyz
    python3 execution/instagram_write.py insights --id IG-001 --reach 1450 --views 2300 --likes 96 \\
        --comments 12 --shares 18 --saves 41 --follows 9 --profile-visits 60 --watch-time 7.5
    python3 execution/instagram_write.py report
"""

import argparse
import re
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import load_workbook

from instagram_tracker import (
    DEFAULT_OUTPUT,
    FOLLOWERS_LAST_ROW,
    FORMATS,
    INSIGHT_COLS,
    INSIGHTS_LAST_ROW,
    METRICS,
    PILLAR_ROWS,
    PLAN_COLS,
    PERCENT_METRICS,
    FREQ_END_CELL,
    FREQ_START_CELL,
    GOAL_CELL,
    GOAL_DATE_CELL,
    SLOT_SETTINGS_COL,
    SLOTS,
    PLAN_LAST_ROW,
    RATE_SCALE,
    RATES,
    SchemaError,
    check_schema,
    STATUSES,
    VERDICTS,
    WEEKDAYS,
)

BACKUP_DIR = DEFAULT_OUTPUT.parent / "backups"
MAX_BACKUPS = 50
OPEN_STATUSES = {s for s in STATUSES if s not in ("Posted", "Skipped")}


class TrackerError(Exception):
    pass


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def check_lock_file(path: Path):
    lock = path.parent / f"~${path.name}"
    if lock.exists():
        print(f"⚠  {lock.name} found — the tracker looks open in Excel. Saving from Excel "
              "afterwards would overwrite this change; close it there first.", file=sys.stderr)


def backup(path: Path):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, BACKUP_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{path.name}")
    for old in sorted(BACKUP_DIR.glob(f"*_{path.name}"))[:-MAX_BACKUPS]:
        old.unlink()


def parse_date(s):
    if s in (None, ""):
        return date.today()
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise TrackerError(f"Date '{s}' must be YYYY-MM-DD.")


def as_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


def fmt_date(d):
    return d.strftime("%a %-d %b") if d else "unscheduled"


def choose(value, choices, field):
    if value in (None, ""):
        return None
    for c in choices:
        if c.lower() == value.strip().lower():
            return c
    raise TrackerError(f"{field} '{value}' isn't one of: {', '.join(choices)}")


def pillars(wb):
    ws = wb["Settings"]
    return [str(ws.cell(row=r, column=4).value).strip() for r in PILLAR_ROWS
            if ws.cell(row=r, column=4).value not in (None, "")]


def resolve_pillar(wb, value, add_new):
    """Pillars drive the Dashboard's by-pillar table, so a near-miss spelling
    would silently split one pillar into two. Match case-insensitively; only
    add a genuinely new pillar when asked to."""
    if value in (None, ""):
        return None
    existing = pillars(wb)
    for p in existing:
        if p.lower() == value.strip().lower():
            return p
    if not add_new:
        raise TrackerError(f"Pillar '{value}' isn't in Settings. Known: {', '.join(existing) or '(none yet)'}. "
                           "Re-run with --new-pillar to add it.")
    ws = wb["Settings"]
    for r in PILLAR_ROWS:
        if ws.cell(row=r, column=4).value in (None, ""):
            ws.cell(row=r, column=4, value=value.strip())
            return value.strip()
    raise TrackerError("All 10 pillar slots in Settings are full.")


def posting_weekdays(wb, slot="Lunch"):
    ws = wb["Settings"]
    col = SLOT_SETTINGS_COL[slot]
    days = {i for i, _ in enumerate(WEEKDAYS)
            if str(ws.cell(row=i + 2, column=col).value or "").strip().lower() == "yes"}
    if not days:
        raise TrackerError(f"No {slot.lower()} posting days are set to 'Yes' in Settings.")
    return days


def default_slot(pillar, angle):
    """The daily vlog (START video + START caption) is the lunchtime series;
    everything else is an evening reach post."""
    return "Lunch" if pillar == "START" and angle in (None, "", "START") else "Evening"


def plan_rows(ws):
    """Yield (row, record) for every non-empty Content Plan row."""
    for r in range(2, PLAN_LAST_ROW + 1):
        idea = ws.cell(row=r, column=PLAN_COLS["idea"]).value
        pid = ws.cell(row=r, column=PLAN_COLS["id"]).value
        if idea in (None, "") and pid in (None, ""):
            continue
        rec = {k: ws.cell(row=r, column=c).value for k, c in PLAN_COLS.items() if k != "day"}
        rec["date"] = as_date(rec["date"])
        rec["posted_date"] = as_date(rec["posted_date"])
        yield r, rec


def first_blank(ws, last, col=1, start=2):
    for r in range(start, last + 1):
        if ws.cell(row=r, column=col).value in (None, ""):
            return r
    raise TrackerError(f"No blank rows left on '{ws.title}' (up to row {last}).")


def next_id(ws):
    nums = []
    for _, rec in plan_rows(ws):
        pid = str(rec["id"] or "")
        if pid.startswith("IG-") and pid[3:].isdigit():
            nums.append(int(pid[3:]))
    return f"IG-{(max(nums) if nums else 0) + 1:03d}"


def next_free_day(wb, ws, start, slot="Lunch"):
    taken = {rec["date"] for _, rec in plan_rows(ws)
             if rec["date"] and rec["status"] != "Skipped" and (rec.get("slot") or "Lunch") == slot}
    days = posting_weekdays(wb, slot)
    d = start
    for _ in range(730):
        if d.weekday() in days and d not in taken:
            return d
        d += timedelta(days=1)
    raise TrackerError("Couldn't find a free posting day in the next two years.")


def find_post(ws, pid):
    pid = pid.strip().upper()
    for r, rec in plan_rows(ws):
        if str(rec["id"] or "").upper() == pid:
            return r, rec
    raise TrackerError(f"No post with ID {pid} in Content Plan.")


def describe(rec):
    bits = [f"{rec['id']} · {fmt_date(rec['date'])}" + (f" ({rec['slot'].lower()})" if rec.get("slot") else "")]
    if rec.get("format"):
        bits.append(rec["format"])
    if rec.get("pillar") or rec.get("angle"):
        label = rec.get("pillar") or "?"
        if rec.get("angle") and rec.get("angle") != rec.get("pillar"):
            label += f" video / {rec['angle']} caption"
        bits.append(label)
    bits.append(rec.get("status") or "Idea")
    lines = [" · ".join(bits), f"    Idea: {rec['idea']}"]
    if rec.get("hook"):
        lines.append(f"    Hook: {rec['hook']}")
    if rec.get("caption"):
        lines.append(f"    Caption notes: {rec['caption']}")
    if rec.get("testing"):
        lines.append(f"    Testing: {rec['testing']}")
    if rec.get("variant_of"):
        lines.append(f"    Variant of: {rec['variant_of']}")
    if rec.get("follow_reason"):
        lines.append(f"    Follow reason: {rec['follow_reason']}")
    if rec.get("verdict"):
        lines.append(f"    Verdict: {rec['verdict']}")
    if rec.get("notes"):
        lines.append(f"    Notes: {rec['notes']}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Commands — return (changed: bool, output lines)
# --------------------------------------------------------------------------
def cmd_idea(wb, a):
    ws = wb["Content Plan"]
    fmt = choose(a.format, FORMATS, "Format")
    pillar = resolve_pillar(wb, a.pillar, a.new_pillar)
    angle = resolve_pillar(wb, a.angle, a.new_pillar)
    slot = choose(a.slot, SLOTS, "Slot") or default_slot(pillar, angle)
    if a.unscheduled:
        when, status = None, "Idea"
    else:
        when = parse_date(a.date) if a.date else next_free_day(wb, ws, date.today(), slot)
        status = "Scheduled"
    r = first_blank(ws, PLAN_LAST_ROW, col=PLAN_COLS["idea"])
    pid = next_id(ws)
    variant = find_post(ws, a.variant_of)[1]["id"] if a.variant_of else None
    values = {"id": pid, "date": when, "slot": slot, "idea": a.idea.strip(), "format": fmt, "pillar": pillar,
              "angle": angle, "testing": a.testing, "variant_of": variant,
              "follow_reason": a.follow_reason, "hook": a.hook, "caption": a.caption, "status": status, "notes": a.notes}
    for k, v in values.items():
        if v not in (None, ""):
            ws.cell(row=r, column=PLAN_COLS[k], value=v)
    return True, ["Added:", describe(values)]


def cmd_schedule(wb, a):
    ws = wb["Content Plan"]
    out = []
    for r, rec in plan_rows(ws):
        if rec["idea"] in (None, ""):
            continue
        changed = False
        if not rec["id"]:
            rec["id"] = next_id(ws)
            ws.cell(row=r, column=PLAN_COLS["id"], value=rec["id"])
            changed = True
        # Blank status = typed straight into the sheet. "Idea" = deliberately
        # banked with --unscheduled, so leave it alone unless asked.
        bankable = (None, "", "Idea") if a.include_bank else (None, "")
        if not rec["date"] and rec["status"] in bankable:
            rec["slot"] = rec.get("slot") or default_slot(rec.get("pillar"), rec.get("angle"))
            ws.cell(row=r, column=PLAN_COLS["slot"], value=rec["slot"])
            rec["date"] = next_free_day(wb, ws, date.today(), rec["slot"])
            rec["status"] = "Scheduled"
            ws.cell(row=r, column=PLAN_COLS["date"], value=rec["date"])
            ws.cell(row=r, column=PLAN_COLS["status"], value="Scheduled")
            changed = True
        if changed:
            out.append(describe(rec))
    return bool(out), (["Scheduled:"] + out) if out else ["Nothing to schedule — every idea already has a date."]


def cmd_today(wb, a):
    ws = wb["Content Plan"]
    day = parse_date(a.date)
    rows = [rec for _, rec in plan_rows(ws)]
    slot_order = lambda rec: SLOTS.index(rec["slot"]) if rec.get("slot") in SLOTS else 0
    todays = sorted((rec for rec in rows if rec["date"] == day and rec["status"] != "Skipped"), key=slot_order)
    missed = [rec for rec in rows if rec["date"] and rec["date"] < day and rec["status"] in OPEN_STATUSES]
    out = [f"📅 {day:%A %-d %B}"]
    if todays:
        out += [describe(rec) for rec in todays]
    else:
        out.append("Nothing planned for this day.")
        upcoming = sorted((rec for rec in rows if rec["date"] and rec["date"] > day
                           and rec["status"] in OPEN_STATUSES), key=lambda x: x["date"])
        if upcoming:
            out += ["Next up:", describe(upcoming[0])]
    if missed:
        out.append(f"\n⚠  {len(missed)} earlier post(s) not marked posted:")
        out += [f"    {rec['id']} · {fmt_date(rec['date'])} · {rec['idea']}" for rec in missed]
    unscheduled = [rec for rec in rows if not rec["date"] and rec["status"] in (None, "", "Idea")]
    if unscheduled:
        out.append(f"\n💡 {len(unscheduled)} idea(s) in the bank without a date.")
    return False, out


def cmd_upcoming(wb, a):
    ws = wb["Content Plan"]
    start = parse_date(a.date)
    end = start + timedelta(days=a.days - 1)
    rows = sorted((rec for _, rec in plan_rows(ws)
                   if rec["date"] and start <= rec["date"] <= end and rec["status"] != "Skipped"),
                  key=lambda x: (x["date"], SLOTS.index(x["slot"]) if x.get("slot") in SLOTS else 0))
    if not rows:
        return False, [f"Nothing planned {fmt_date(start)} – {fmt_date(end)}."]
    return False, [describe(rec) for rec in rows]


def is_fast_lane(rec):
    """The daily START vlog skips research and design, but never hooks (00_pipeline.md)."""
    return rec.get("slot") == "Lunch" and rec.get("pillar") == "START"


def next_step(rec):
    status = rec.get("status") or "Idea"
    fast, carousel = is_fast_lane(rec), rec.get("format") == "Carousel"
    return {
        "Idea": "Producer: date it or leave it banked",
        "Scheduled": "Producer: intake questions" + ("" if fast else " → Researcher note"),
        "Briefed": "Hook Generator: 3 options → she picks",
        "Hooked": "Carousel Builder: slide outline + caption" if carousel
                  else "Copywriter: on-screen story + caption",
        "Drafted": "Producer: QA → her approval" if fast
                   else "Carousel Builder + Designer: build in Canva" if carousel else "Designer: cover",
        "Built": "Producer: QA → her approval",
        "Approved": f"Post it, then: posted --id {rec['id']}",
    }.get(status, "")


def cmd_pipeline(wb, a):
    ws = wb["Content Plan"]
    today = parse_date(a.date)
    horizon = today + timedelta(days=a.days)
    rows = [rec for _, rec in plan_rows(ws) if (rec.get("status") or "Idea") in OPEN_STATUSES]
    dated = [rec for rec in rows if rec["date"] and rec["date"] <= horizon]
    banked = [rec for rec in rows if not rec["date"]]
    out = [f"Pipeline · {fmt_date(today)} to {fmt_date(horizon)}"]
    for status in STATUSES:
        group = sorted((rec for rec in dated if (rec.get("status") or "Idea") == status), key=lambda x: x["date"])
        if not group:
            continue
        out.append(f"\n{status} ({len(group)})")
        for rec in group:
            days = (rec["date"] - today).days
            flag = "  ⚠ overdue" if days < 0 else "  ⚠ due within a day" if days <= 1 and status != "Approved" else ""
            lane = " · fast lane" if is_fast_lane(rec) else ""
            out.append(f"  {rec['id']} · {fmt_date(rec['date'])} · {rec.get('format') or '?'}{lane} · "
                       f"{rec['idea']}{flag}")
            out.append(f"      next: {next_step(rec)}")
    if len(out) == 1:
        out.append("Nothing open in this window.")
    if banked:
        out.append(f"\n💡 {len(banked)} idea(s) in the bank without a date.")
    return False, out


def cmd_move(wb, a):
    ws = wb["Content Plan"]
    r, rec = find_post(ws, a.id)
    if a.bank:
        was = fmt_date(rec["date"])
        ws.cell(row=r, column=PLAN_COLS["date"]).value = None
        ws.cell(row=r, column=PLAN_COLS["status"], value="Idea")
        return True, [f"Banked {rec['id']} (was {was}): no date, status Idea."]
    if not a.date:
        raise TrackerError("Pass --date YYYY-MM-DD, or --bank to pull it out of the schedule.")
    new = parse_date(a.date)
    slot = choose(a.slot, SLOTS, "Slot") or rec.get("slot") or "Lunch"
    ws.cell(row=r, column=PLAN_COLS["date"], value=new)
    ws.cell(row=r, column=PLAN_COLS["slot"], value=slot)
    if rec["status"] in (None, "", "Idea"):
        ws.cell(row=r, column=PLAN_COLS["status"], value="Scheduled")
    clash = [x["id"] for _, x in plan_rows(ws) if x["date"] == new and x["id"] != rec["id"]
             and x["status"] != "Skipped" and (x.get("slot") or "Lunch") == slot]
    out = [f"Moved {rec['id']} from {fmt_date(rec['date'])} to {fmt_date(new)} ({slot.lower()})."]
    if clash:
        out.append(f"Note: {', '.join(clash)} is also planned in that slot.")
    return True, out


def cmd_edit(wb, a):
    """Change a post's details. Format/pillar/idea are mirrored onto its
    Insights row so the Dashboard groups it correctly."""
    ws = wb["Content Plan"]
    r, rec = find_post(ws, a.id)
    changes = {
        "idea": a.idea,
        "format": choose(a.format, FORMATS, "Format"),
        "pillar": resolve_pillar(wb, a.pillar, a.new_pillar),
        "angle": resolve_pillar(wb, a.angle, a.new_pillar),
        "hook": a.hook, "caption": a.caption, "notes": a.notes, "link": a.link,
        "testing": a.testing, "follow_reason": a.follow_reason,
        "variant_of": find_post(ws, a.variant_of)[1]["id"] if a.variant_of else None,
        "verdict": choose(a.verdict, VERDICTS, "Verdict"),
        "slot": choose(a.slot, SLOTS, "Slot"),
    }
    changes = {k: v for k, v in changes.items() if v not in (None, "")}
    if "pillar" in changes and "notes" not in changes and "needs a pillar" in str(rec["notes"] or ""):
        ws.cell(row=r, column=PLAN_COLS["notes"]).value = None
        rec["notes"] = None
    if not changes:
        raise TrackerError("Nothing to change — pass e.g. --pillar PROVE or --hook \"...\".")
    for k, v in changes.items():
        ws.cell(row=r, column=PLAN_COLS[k], value=v)
    ins = wb["Insights"]
    for ir in range(2, INSIGHTS_LAST_ROW + 1):
        if str(ins.cell(row=ir, column=1).value or "").upper() == rec["id"].upper():
            for k in ("idea", "format", "pillar", "angle"):
                if k in changes:
                    ins.cell(row=ir, column=INSIGHT_COLS[k], value=changes[k])
            break
    rec.update(changes)
    return True, ["Updated:", describe(rec)]


def cmd_status(wb, a):
    ws = wb["Content Plan"]
    r, rec = find_post(ws, a.id)
    status = choose(a.status, STATUSES, "Status")
    ws.cell(row=r, column=PLAN_COLS["status"], value=status)
    return True, [f"{rec['id']} → {status}"]


def cmd_posted(wb, a):
    ws = wb["Content Plan"]
    r, rec = find_post(ws, a.id)
    when = parse_date(a.date)
    ws.cell(row=r, column=PLAN_COLS["status"], value="Posted")
    ws.cell(row=r, column=PLAN_COLS["posted_date"], value=when)
    if a.link:
        ws.cell(row=r, column=PLAN_COLS["link"], value=a.link)
    return True, [f"{rec['id']} marked posted on {fmt_date(when)}: {rec['idea']}"]


def upsert_insights(wb, pr, rec, metrics, captured, posted=None, notes=None):
    """Write one post's metrics into Insights (one row per post) and mark it
    Posted in the plan. Metrics not given are left as they were, so a
    screenshot-only figure (e.g. follows) survives an API sync and vice versa.
    Returns (row, updating)."""
    plan, ws = wb["Content Plan"], wb["Insights"]
    row, updating = None, False
    for r in range(2, INSIGHTS_LAST_ROW + 1):
        if str(ws.cell(row=r, column=1).value or "").upper() == rec["id"].upper():
            row, updating = r, True
            break
    if row is None:
        row = first_blank(ws, INSIGHTS_LAST_ROW)

    posted = rec["posted_date"] or posted or rec["date"] or date.today()
    if rec["status"] != "Posted" or not rec["posted_date"]:
        plan.cell(row=pr, column=PLAN_COLS["status"], value="Posted")
        plan.cell(row=pr, column=PLAN_COLS["posted_date"], value=posted)

    base = {"id": rec["id"], "posted_date": posted, "format": rec["format"], "pillar": rec["pillar"],
            "angle": rec.get("angle"),
            "idea": rec["idea"], "captured": captured}
    for k, v in {**base, **metrics}.items():
        ws.cell(row=row, column=INSIGHT_COLS[k], value=v)
    if notes:
        ws.cell(row=row, column=INSIGHT_COLS["notes"], value=notes)
    return row, updating


def cmd_insights(wb, a):
    pr, rec = find_post(wb["Content Plan"], a.id)
    ws = wb["Insights"]
    metrics = {m: int(v) if float(v).is_integer() else v
               for m in METRICS if (v := getattr(a, m)) is not None}
    if not metrics:
        raise TrackerError("Give at least one metric (e.g. --reach 1200 --saves 30).")
    for m, v in metrics.items():
        if v < 0:
            raise TrackerError(f"{m} can't be negative.")
    for m in PERCENT_METRICS & metrics.keys():
        # Given as a percentage as Instagram shows it (72 = 72%); stored as a fraction.
        if metrics[m] > 100:
            raise TrackerError(f"--{m.replace('_', '-')} is a percentage between 0 and 100.")
        metrics[m] = metrics[m] / 100

    row, updating = upsert_insights(wb, pr, rec, metrics, parse_date(a.captured),
                                    parse_date(a.posted_date) if a.posted_date else None, a.notes)

    reach = ws.cell(row=row, column=INSIGHT_COLS["reach"]).value
    label = lambda k, v: f"{k.replace('_', ' ')} {v:.0%}" if k in PERCENT_METRICS else f"{k.replace('_', ' ')} {v:,g}"
    out = [f"{'Updated' if updating else 'Logged'} insights for {rec['id']} ({rec['idea']}):",
           "    " + " · ".join(label(k, v) for k, v in metrics.items())]
    if reach:
        n = lambda k: ws.cell(row=row, column=INSIGHT_COLS[k]).value or 0
        er = (n("likes") + n("comments") + n("shares") + n("saves")) / reach
        out.append(f"    engagement {er:.1%} · save rate {n('saves') / reach:.1%} · share rate {n('shares') / reach:.1%}")
    else:
        out.append("    (no reach yet — rates will fill in once reach is logged)")
    return True, out


def cmd_followers(wb, a):
    ws = wb["Followers"]
    when = parse_date(a.date)
    r = first_blank(ws, FOLLOWERS_LAST_ROW, col=2)
    prev = ws.cell(row=r - 1, column=2).value if r > 2 else None
    ws.cell(row=r, column=1, value=when)
    ws.cell(row=r, column=2, value=a.count)
    if a.notes:
        ws.cell(row=r, column=4, value=a.notes)
    change = f" ({a.count - prev:+d} since last entry)" if isinstance(prev, (int, float)) else ""
    return True, [f"Followers on {fmt_date(when)}: {a.count:,}{change}"]


def load_posts(wb):
    """Every Insights row as a dict, with rates computed the same way as the
    sheet (blank metric → blank rate, never 0) and the plan's test fields
    (verdict, testing, variant_of, row) joined on."""
    ws = wb["Insights"]
    plan = {str(rec["id"]).upper(): (r, rec) for r, rec in plan_rows(wb["Content Plan"]) if rec["id"]}
    posts = []
    for r in range(2, INSIGHTS_LAST_ROW + 1):
        if ws.cell(row=r, column=1).value in (None, ""):
            continue
        pid = str(ws.cell(row=r, column=1).value).upper()
        # A row whose Content Plan status is Skipped (e.g. a sync-created
        # duplicate merged into another ID) never counts in reports/patterns.
        if plan.get(pid, (None, {}))[1].get("status") == "Skipped":
            continue
        p = {k: ws.cell(row=r, column=c).value for k, c in INSIGHT_COLS.items()}
        p["posted_date"] = as_date(p["posted_date"])
        reach = p["reach"] or 0
        g = lambda k: p[k] or 0
        p["er"] = (g("likes") + g("comments") + g("shares") + g("saves")) / reach if reach else None
        for rate, metric in RATES.items():
            # Blank metric = not measured (e.g. follows on reels), not zero.
            p[rate] = p[metric] / reach * RATE_SCALE.get(rate, 1) if reach and p[metric] is not None else None
        p["plan_row"], rec = plan.get(str(p["id"]).upper(), (None, {}))
        for k in ("verdict", "testing", "variant_of", "follow_reason", "hook", "slot"):
            p[k] = rec.get(k)
        posts.append(p)
    return posts


def fmt_rate(key, v, digits=1):
    if v is None:
        return "–"
    return f"{v:.{digits}f}/1k" if key in RATE_SCALE else f"{v:.{digits}%}"


def cover_text(hook):
    """Pull just the cover line out of a Hook field like 'Cover: X · Label: Y
    [frame: ...]' or 'Cover (as posted): X [frame: ...]'. Falls back to the
    raw string for posts logged before this format (e.g. a bare cover line)."""
    if not hook:
        return None
    s = str(hook)
    m = re.match(r"^Cover(?:\s*\([^)]*\))?\s*:\s*(.+)", s, re.IGNORECASE)
    if m:
        s = m.group(1)
    s = re.split(r"\s*·\s*Label:", s)[0]
    s = re.split(r"\s*\[frame:", s)[0]
    s = s.strip()
    return s or None


def classify_cover(text):
    """Structural buckets a cover line can be read against. Kept simple and
    legible on purpose — a human should be able to see why a cover landed
    in a bucket, not trust a black box."""
    words = text.split()
    tags = []
    tags.append("question" if text.rstrip().endswith("?") else "statement")
    tags.append("short (≤6 words)" if len(words) <= 6 else "long (7+ words)")
    if re.search(r"\bto the mum\b", text, re.IGNORECASE):
        tags.append('"to the mum" direct address')
    if re.search(r"\d", text):
        tags.append("has a number")
    return tags


def overlay_text(p):
    """The first on-screen line a feed viewer actually sees. The cover is only
    shown on the profile grid and often differs from the opening overlay, so
    skip rate has to be read against this, not the cover. Taken from an
    'Overlay: …' part of the Hook field, else the post file's first
    On-screen story row."""
    hook = str(p.get("hook") or "")
    m = re.search(r"(?:First overlay|Overlay)\s*:\s*(.+?)(?:\s*·|\s*\[frame:|$)", hook, re.IGNORECASE)
    if m and not m.group(1).lower().startswith(("n/a", "(")):
        return m.group(1).strip().split(" / ")[0]
    from instagram_post import find_existing_post_file, sections
    f = find_existing_post_file(p["id"])
    if not f:
        return None
    sec = sections(f.read_text())
    story = next((sec[k] for k in sec if k.startswith("on-screen")), "")
    for row in story.splitlines():
        cells = [c.strip() for c in row.strip("|").split("|")]
        if len(cells) > 1 and cells[1] and not set(cells[1]) <= set("-") \
                and cells[1] != "Text on screen" and not cells[1].startswith("("):
            return cells[1]
    return None


def _bucket_table(rated, text_of, metric, key, label):
    buckets = {}
    for p in rated:
        for tag in classify_cover(text_of(p)):
            buckets.setdefault(tag, []).append(p)
    out = []
    for tag, ps in sorted(buckets.items(), key=lambda kv: key(kv[1])):
        flag = "" if len(ps) >= 3 else "  (early signal, n<3)"
        out.append(f"  {tag}: {len(ps)} post(s) · {label} {metric(ps)}{flag}")
    return buckets, out


def cmd_patterns(wb, a):
    """Structural patterns in what's actually held attention and converted,
    so a recommendation can be checked against real history. Two separate
    jobs (her correction, 23 Oct 2026): the OPENING OVERLAY is what a feed
    viewer sees, so it's read against skip rate; the COVER is only seen on the
    profile grid, so it's read against follows. Built 9 Oct 2026."""
    posts = load_posts(wb)
    avg = lambda xs: sum(xs) / len(xs) if xs else None
    out = []

    feed = [(p, overlay_text(p)) for p in posts if p.get("skip_rate") is not None]
    feed = [(p, t) for p, t in feed if t]
    out.append(f"FEED · opening overlay vs skip rate ({len(feed)} reel(s) with a known first overlay)")
    out.append("Lower skip = held attention better. Buckets under 3 posts are an early signal, not a rule.")
    if feed:
        olay = {p["id"]: t for p, t in feed}
        buckets, rows = _bucket_table([p for p, _ in feed], lambda p: olay[p["id"]],
                                      lambda ps: f"{avg([x['skip_rate'] for x in ps]):.0%}",
                                      lambda ps: avg([x["skip_rate"] for x in ps]), "avg skip")
        out += rows
        q, s = buckets.get("question"), buckets.get("statement")
        if q and s and len(q) >= 2 and len(s) >= 2:
            qs, ss = avg([x["skip_rate"] for x in q]), avg([x["skip_rate"] for x in s])
            out.append(f"→ Opening lines: {'statements' if ss < qs else 'questions'} hold better "
                       f"(statements {ss:.0%} vs questions {qs:.0%} avg skip).")
    else:
        out.append("  (no first overlays known yet — log them as 'Overlay: …' in the Hook field)")

    grid = [p for p in posts if p.get("follow_rate") is not None and cover_text(p.get("hook"))]
    out.append(f"\nGRID · cover vs follows per 1k reached ({len(grid)} post(s) with follows logged)")
    out.append("The cover is only seen by profile visitors, so it's judged on converting them, not on skip.")
    if grid:
        _, rows = _bucket_table(grid, lambda p: cover_text(p["hook"]),
                                lambda ps: f"{avg([x['follow_rate'] for x in ps]):.1f}/1k",
                                lambda ps: -avg([x["follow_rate"] for x in ps]), "avg follows")
        out += rows

    missing = [p["id"] for p in posts if p.get("skip_rate") is not None and not overlay_text(p)]
    if missing:
        out.append(f"\n({len(missing)} reel(s) have a skip rate but no known first overlay: {', '.join(missing[:10])}"
                   f"{'…' if len(missing) > 10 else ''})")
    return False, out


def cmd_report(wb, a):
    posts = load_posts(wb)
    if not posts:
        return False, ["No insights logged yet."]

    with_reach = [p for p in posts if p["er"] is not None]
    out = [f"{len(posts)} post(s) tracked."]

    def top(title, key, fmt):
        ranked = sorted((p for p in posts if p.get(key) is not None), key=lambda p: p[key], reverse=True)[:a.top]
        if ranked:
            out.append(f"\nTop by {title}:")
            out.extend(f"    {p['id']} · {p['format'] or '-'} · {p['pillar'] or '-'} · {fmt(p[key])} · {p['idea']}"
                       for p in ranked)

    top("reach", "reach", lambda v: f"{v:,.0f}")
    top("engagement rate", "er", lambda v: f"{v:.1%}")
    top("save rate", "save_rate", lambda v: f"{v:.1%}")
    top("non-follower reach", "non_follower_pct", lambda v: f"{v:.0%}")
    top("follows per 1k reached", "follow_rate", lambda v: f"{v:.1f}")
    top("viewers aged 25–44 (Sally)", "sally_age_pct", lambda v: f"{v:.0%}")

    def group(title, key):
        buckets = {}
        for p in with_reach:
            buckets.setdefault(p[key] or "(none)", []).append(p)
        if not buckets:
            return
        out.append(f"\nBy {title}:")
        for name, ps in sorted(buckets.items(), key=lambda kv: -sum(x["er"] for x in kv[1]) / len(kv[1])):
            def avg(k, fmt=".1%"):
                vals = [x[k] for x in ps if x.get(k) is not None]
                if k in RATE_SCALE:
                    fmt = ".1f"
                return format(sum(vals) / len(vals), fmt) if vals else "–"
            out.append(f"    {name}: {len(ps)} post(s) · avg reach {avg('reach', ',.0f')} · engagement {avg('er')} · "
                       f"saves {avg('save_rate')} · shares {avg('share_rate')} · comments {avg('comment_rate')} · "
                       f"visits {avg('visit_rate')} · follows/1k {avg('follow_rate')} · skip {avg('skip_rate', '.0%')}")

    group("format", "format")
    group("pillar (video)", "pillar")
    group("caption angle", "angle")

    # Video × caption pairs — the real question is which caption framing
    # gets the most out of each kind of video.
    pairs = {}
    for p in with_reach:
        if p["pillar"] and p["angle"]:
            pairs.setdefault(f"{p['pillar']} video + {p['angle']} caption", []).append(p)
    if pairs:
        out.append("\nVideo + caption combinations:")
        for name, ps in sorted(pairs.items(), key=lambda kv: -sum(x["reach"] for x in kv[1]) / len(kv[1])):
            reach = sum(x["reach"] for x in ps) / len(ps)
            er = sum(x["er"] for x in ps) / len(ps)
            out.append(f"    {name}: {len(ps)} post(s) · avg reach {reach:,.0f} · engagement {er:.1%}")

    # Which pillar wins each job. Small samples are flagged rather than hidden
    # so early patterns are visible but not over-trusted.
    leaders = [("Non-follower reach", "non_follower_pct"), ("Save rate", "save_rate"),
               ("Share rate", "share_rate"), ("Comment rate", "comment_rate"),
               ("Profile visit rate", "visit_rate"), ("Follows per 1k", "follow_rate"),
               ("Lowest skip rate", "skip_rate")]
    lines = []
    for label, key in leaders:
        buckets = {}
        for p in with_reach:  # by video pillar — the content itself
            if p["pillar"] and p.get(key) is not None:
                buckets.setdefault(p["pillar"], []).append(p[key])
        if not buckets:
            continue
        pick = min if key == "skip_rate" else max  # lower skip rate is better
        name, vals = pick(buckets.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
        caveat = "" if len(vals) >= 3 else f"  (only {len(vals)} post{'s' if len(vals) > 1 else ''} — too early to call)"
        lines.append(f"    {label}: {name} {fmt_rate(key, sum(vals) / len(vals))}{caveat}")
    if lines:
        out += ["\nPillar leaders (by video):"] + lines
    return False, out


def median(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2


MIN_FOR_MEDIAN = 3  # posts with a metric before its median means anything


def suggest_verdict(p, medians):
    """Win/Mixed/Flop against the account's own medians. Follows per 1k is
    the deciding number when known (the goal is followers who stay); until a
    screenshot supplies it, reach + sends + saves stand in. Suggestions only —
    Claude confirms with the user before writing a verdict."""
    if p["follow_rate"] is not None and medians["follow_rate"] and medians["follow_rate_n"] >= MIN_FOR_MEDIAN:
        key, basis = "follow_rate", "follows/1k"
    elif p["follow_rate"] is not None:
        key, basis = "reach", f"reach (follows logged on <{MIN_FOR_MEDIAN} posts, can't compare yet)"
    else:
        key, basis = "reach", "reach (no follows yet)"
    m = medians[key]
    if not m or p.get(key) is None:
        return None, basis
    ratio = p[key] / m
    # A post that pulls well but nobody sends or saves is reach without interest.
    depth = (p["share_rate"] or 0) + (p["save_rate"] or 0)
    depth_m = (medians["share_rate"] or 0) + (medians["save_rate"] or 0)
    if ratio >= 1.5:
        if key == "follow_rate" or depth >= depth_m:
            return "Win", f"{basis} {ratio:.1f}× your median"
        return "Mixed", f"{basis} {ratio:.1f}× your median, but sends+saves below median"
    if ratio <= 0.5:
        return "Flop", f"{basis} {ratio:.1f}× your median"
    return "Mixed", f"{basis} {ratio:.1f}× your median"


def cmd_review(wb, a):
    """The Sunday loop: goal pace, screenshots needed, verdicts to confirm,
    winners to remix, and what the next 7 days are testing."""
    today = parse_date(a.date)
    posts = load_posts(wb)
    out = [f"📋 Weekly review · {today:%a %-d %b}"]

    # 1. Goal pace
    st = wb["Settings"]
    goal, goal_date = st[GOAL_CELL].value, as_date(st[GOAL_DATE_CELL].value)
    fw = wb["Followers"]
    log = [(as_date(fw.cell(row=r, column=1).value), fw.cell(row=r, column=2).value)
           for r in range(2, FOLLOWERS_LAST_ROW + 1) if fw.cell(row=r, column=2).value is not None]
    if log and goal and goal_date:
        now_date, now = log[-1]
        week_ago = [n for d, n in log if d and d <= now_date - timedelta(days=7)]
        days_left = max(1, (goal_date - today).days)
        needed = max(0, goal - now) / days_left
        line = f"Followers {now:,} of {goal:,} by {goal_date:%-d %b} → need {needed:,.0f}/day"
        if week_ago:
            line += f" · last 7 days: {(now - week_ago[-1]) / 7:+,.1f}/day"
        else:
            line += " · (pace shows once there's a week of follower history)"
        out.append(line)

    # 2. Screenshots needed: 5+ days old, follows or non-follower % missing
    shots = [p for p in posts if p["posted_date"] and (today - p["posted_date"]).days >= 5
             and (p["follows"] is None or p["non_follower_pct"] is None or p.get("sally_age_pct") is None)]
    if shots:
        out.append(f"\n📸 Screenshot these posts' insights ({len(shots)}): follows + non-follower % + Audience → Age (25–34 + 35–44)")
        out += [f"    {p['id']} · {p['posted_date']:%a %-d %b} · {p['idea'][:70]}"
                for p in sorted(shots, key=lambda p: p["posted_date"], reverse=True)[:a.limit]]

    # 3. Verdicts to confirm: 7+ days old, no verdict yet
    medians = {k: median(p.get(k) for p in posts) for k in ("reach", "follow_rate", "share_rate", "save_rate")}
    medians["follow_rate_n"] = sum(1 for p in posts if p["follow_rate"] is not None)
    pending = [p for p in posts if p["posted_date"] and (today - p["posted_date"]).days >= 7 and not p["verdict"]]
    if pending:
        out.append(f"\n⚖️  Verdicts to confirm ({len(pending)}), suggested against your medians:")
        for p in sorted(pending, key=lambda p: p["posted_date"]):
            v, why = suggest_verdict(p, medians)
            out.append(f"    {p['id']} · {p['pillar'] or '?'} video / {p['angle'] or '?'} caption · "
                       f"suggest {v or '?'} ({why}) · {p['idea'][:50]}")
            if p["testing"]:
                out.append(f"        was testing: {p['testing']}")

    # 4. Remix candidates: Wins, best first; fall back to top reach if none yet
    wins = [p for p in posts if p["verdict"] == "Win"]
    pool = wins or sorted((p for p in posts if p["reach"]), key=lambda p: p["reach"], reverse=True)[:3]
    if pool:
        key = lambda p: (p["follow_rate"] or 0, p["reach"] or 0)
        out.append("\n🔁 Remix these (same video type, new hook):" if wins
                   else "\n🔁 No confirmed Wins yet; strongest reach so far:")
        for p in sorted(pool, key=key, reverse=True)[:3]:
            remixes = sum(1 for _, rec in plan_rows(wb["Content Plan"]) if rec.get("variant_of") == p["id"])
            out.append(f"    {p['id']} · {p['pillar'] or '?'} / {p['angle'] or '?'} · reach {p['reach']:,} · "
                       f"follows/1k {fmt_rate('follow_rate', p['follow_rate'])} · {remixes} remix(es) planned · {p['idea'][:50]}")

    # 4b. Reach-vs-follows mismatch: the thing a reach-only skim would miss.
    # Built 9 Oct 2026 so this is a standing check every Sunday, not
    # something that only surfaces when someone happens to go looking for it
    # (that's exactly how the week-1 LinkedIn finding — "reach picked the
    # wrong post" — got found: by hand, once).
    with_both = [p for p in posts if p["reach"] and p["follow_rate"] is not None]
    if len(with_both) >= MIN_FOR_MEDIAN:
        by_reach = sorted(with_both, key=lambda p: p["reach"], reverse=True)
        by_follow = sorted(with_both, key=lambda p: p["follow_rate"], reverse=True)
        top_reach_ids = {p["id"] for p in by_reach[:3]}
        top_follow_ids = {p["id"] for p in by_follow[:3]}
        mismatches = [p for p in by_reach[:3] if p["id"] not in top_follow_ids]
        if mismatches:
            out.append("\n⚠️  Reach-vs-follows mismatch (top-3 reach, not top-3 follows/1k):")
            for p in mismatches:
                out.append(f"    {p['id']} · reach {p['reach']:,} but only {fmt_rate('follow_rate', p['follow_rate'])} "
                           f"· {p['idea'][:50]}")
            out.append("    A reach-only read would point the strategy at these — check `patterns` before remixing them.")

    # 5. Posting-frequency test: does a second (evening) post cost the vlog reach?
    out += frequency_check(wb, posts, today)

    # 6. Next 7 days
    upcoming = sorted((rec for _, rec in plan_rows(wb["Content Plan"])
                       if rec["date"] and today <= rec["date"] < today + timedelta(days=7)
                       and rec["status"] in OPEN_STATUSES), key=lambda x: x["date"])
    out.append(f"\n🗓  Next 7 days: {len(upcoming)} post(s) planned")
    for rec in upcoming:
        flag = "" if rec.get("testing") else "  ← no test set"
        out.append(f"    {rec['id']} · {fmt_date(rec['date'])} · {rec.get('pillar') or '?'} / "
                   f"{rec.get('angle') or '?'} · {rec['idea'][:50]}{flag}")
    return False, out


def frequency_check(wb, posts, today):
    """Compare single-post days (vlog only) with double-post days (vlog +
    evening reel) inside the Settings test window. Cannibalisation shows up
    as the lunchtime vlog reaching fewer people on double days; the payoff
    shows up as more total reach and follows per day."""
    st = wb["Settings"]
    start, end = as_date(st[FREQ_START_CELL].value), as_date(st[FREQ_END_CELL].value)
    if not (start and end) or today < start:
        return []
    days = {}
    for p in posts:
        d = p["posted_date"]
        if d and start <= d <= min(end, today):
            days.setdefault(d, []).append(p)
    if not days:
        return [f"\n🧪 Frequency test {fmt_date(start)} – {fmt_date(end)}: no posts synced yet."]
    stats = {"single": {"vlog": [], "total": [], "follows": []}, "double": {"vlog": [], "total": [], "follows": []}}
    young = 0
    for d, ps in days.items():
        kind = "double" if any(p.get("slot") == "Evening" for p in ps) else "single"
        vlogs = [p["reach"] for p in ps if p.get("slot") == "Lunch" and p["reach"] is not None]
        stats[kind]["vlog"] += vlogs
        stats[kind]["total"].append(sum(p["reach"] or 0 for p in ps))
        if all(p["follows"] is not None for p in ps):
            stats[kind]["follows"].append(sum(p["follows"] for p in ps))
        young += sum(1 for p in ps if (today - d).days < 7)
    avg = lambda xs: sum(xs) / len(xs) if xs else None
    f = lambda xs: f"{avg(xs):,.0f} (n={len(xs)})" if xs else "–"
    day_no = (min(today, end) - start).days + 1
    out = [f"\n🧪 Frequency test {fmt_date(start)} – {fmt_date(end)} · day {day_no} of {(end - start).days + 1}",
           f"    Vlog reach      · single days {f(stats['single']['vlog'])} · double days {f(stats['double']['vlog'])}",
           f"    Day total reach · single days {f(stats['single']['total'])} · double days {f(stats['double']['total'])}",
           f"    Follows per day · single days {f(stats['single']['follows'])} · double days {f(stats['double']['follows'])}"]
    sv, dv = avg(stats["single"]["vlog"]), avg(stats["double"]["vlog"])
    if sv and dv:
        out.append(f"    → vlog on double days reaches {dv / sv:.0%} of single days (rule: stay above ~80%)")
    if not stats["double"]["follows"] or not stats["single"]["follows"]:
        out.append("    → follows need screenshots for every post on a day before that day counts")
    from instagram_repurpose import story_days
    stories = story_days(start, min(end, today))
    kinds = {d: ("double" if any(p.get("slot") == "Evening" for p in ps) else "single") for d, ps in days.items()}
    with_story = {k: sum(1 for d, kk in kinds.items() if kk == k and d in stories) for k in ("single", "double")}
    n_kind = {k: sum(1 for kk in kinds.values() if kk == k) for k in ("single", "double")}
    out.append(f"    Story days      · single {with_story['single']}/{n_kind['single']} · double {with_story['double']}/{n_kind['double']}"
               " (Stories are posted freely; logged with instagram_repurpose.py story)")
    share = {k: with_story[k] / n_kind[k] for k in n_kind if n_kind[k]}
    if len(share) == 2 and abs(share["single"] - share["double"]) > 0.4:
        out.append("    ⚠ Stories fell unevenly across single and double days: treat a small vlog-reach gap with caution")
    if young:
        out.append(f"    ({young} post(s) under 7 days old; their reach is still growing)")
    if today > end + timedelta(days=7):
        out.append("    ✅ Test window plus a week has passed: time to decide (see directive's decision rule).")
    return out


def cmd_settings(wb, a):
    ws = wb["Settings"]
    changed = False
    for slot, days_arg in (("Lunch", a.lunch_days or a.days), ("Evening", a.evening_days)):
        if days_arg:
            wanted = {choose(d, WEEKDAYS, "Day") for d in days_arg.split(",") if d.strip()}
            for i, day in enumerate(WEEKDAYS, start=2):
                ws.cell(row=i, column=SLOT_SETTINGS_COL[slot], value="Yes" if day in wanted else "No")
            changed = True
    if a.test_start:
        ws[FREQ_START_CELL] = parse_date(a.test_start)
        changed = True
    if a.test_end:
        ws[FREQ_END_CELL] = parse_date(a.test_end)
        changed = True
    if a.add_pillar:
        resolve_pillar(wb, a.add_pillar, add_new=True)
        changed = True
    if a.remove_pillar:
        names = [p for p in pillars(wb) if p.lower() != a.remove_pillar.strip().lower()]
        if len(names) == len(pillars(wb)):
            raise TrackerError(f"Pillar '{a.remove_pillar}' isn't in Settings.")
        for i, r in enumerate(PILLAR_ROWS):
            # cell(value=None) is a no-op in openpyxl, so assign .value to clear.
            ws.cell(row=r, column=4).value = names[i] if i < len(names) else None
        changed = True
    if a.goal:
        ws[GOAL_CELL] = a.goal
        changed = True
    if a.goal_date:
        ws[GOAL_DATE_CELL] = parse_date(a.goal_date)
        changed = True
    gd = as_date(ws[GOAL_DATE_CELL].value)
    out = [f"{slot} posts: {', '.join(WEEKDAYS[i] for i in sorted(posting_weekdays(wb, slot)))}" for slot in SLOTS]
    ts, te = as_date(ws[FREQ_START_CELL].value), as_date(ws[FREQ_END_CELL].value)
    out += [f"Pillars: {', '.join(pillars(wb)) or '(none yet)'}",
            f"Goal: {ws[GOAL_CELL].value or 0:,} followers by {fmt_date(gd)}"]
    if ts and te:
        out.append(f"Frequency test: {fmt_date(ts)} – {fmt_date(te)}")
    return changed, out


COMMANDS = {
    "idea": cmd_idea, "schedule": cmd_schedule, "today": cmd_today, "upcoming": cmd_upcoming,
    "move": cmd_move, "edit": cmd_edit, "status": cmd_status, "pipeline": cmd_pipeline, "posted": cmd_posted, "insights": cmd_insights,
    "followers": cmd_followers, "report": cmd_report, "patterns": cmd_patterns, "review": cmd_review, "settings": cmd_settings,
}


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--file", default=str(DEFAULT_OUTPUT))

    ap = argparse.ArgumentParser(description="Read and write the Instagram content tracker.", parents=[common])
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("idea", parents=[common])
    p.add_argument("--idea", required=True)
    p.add_argument("--format", help=", ".join(FORMATS))
    p.add_argument("--pillar", help="What the video shows")
    p.add_argument("--angle", help="How the caption frames it (defaults to blank)")
    p.add_argument("--testing", help="The one variable this post tests")
    p.add_argument("--variant-of", dest="variant_of", help="ID of the post this remixes")
    p.add_argument("--follow-reason", dest="follow_reason", help="Why a stranger would follow after watching")
    p.add_argument("--new-pillar", action="store_true", help="Add --pillar/--angle to Settings if new")
    p.add_argument("--hook")
    p.add_argument("--caption")
    p.add_argument("--notes")
    p.add_argument("--date", help="YYYY-MM-DD (default: next free day for the slot)")
    p.add_argument("--slot", help="Lunch or Evening (default: Lunch for the START vlog, Evening otherwise)")
    p.add_argument("--unscheduled", action="store_true", help="Bank the idea without a date")

    p = sub.add_parser("schedule", parents=[common])
    p.add_argument("--include-bank", action="store_true", help="Also date ideas banked with --unscheduled")

    p = sub.add_parser("today", parents=[common])
    p.add_argument("--date", help="YYYY-MM-DD (default: today)")

    p = sub.add_parser("upcoming", parents=[common])
    p.add_argument("--date", help="Start date (default: today)")
    p.add_argument("--days", type=int, default=7)

    p = sub.add_parser("move", parents=[common])
    p.add_argument("--id", required=True)
    p.add_argument("--date", help="YYYY-MM-DD (required unless --bank)")
    p.add_argument("--slot", help="Lunch or Evening (default: keep)")
    p.add_argument("--bank", action="store_true", help="Pull it out of the schedule: clear the date, status back to Idea")

    p = sub.add_parser("edit", parents=[common])
    p.add_argument("--id", required=True)
    for f in ("idea", "format", "pillar", "angle", "hook", "caption", "notes", "link", "testing"):
        p.add_argument(f"--{f}")
    p.add_argument("--variant-of", dest="variant_of")
    p.add_argument("--follow-reason", dest="follow_reason")
    p.add_argument("--verdict", help=", ".join(VERDICTS))
    p.add_argument("--slot", help=", ".join(SLOTS))
    p.add_argument("--new-pillar", action="store_true")

    p = sub.add_parser("status", parents=[common])
    p.add_argument("--id", required=True)
    p.add_argument("--status", required=True, help=", ".join(STATUSES))

    p = sub.add_parser("pipeline", parents=[common])
    p.add_argument("--date", help="As of YYYY-MM-DD (default: today)")
    p.add_argument("--days", type=int, default=14, help="How far ahead to look (default 14)")

    p = sub.add_parser("posted", parents=[common])
    p.add_argument("--id", required=True)
    p.add_argument("--date", help="YYYY-MM-DD (default: today)")
    p.add_argument("--link")

    p = sub.add_parser("insights", parents=[common])
    p.add_argument("--id", required=True)
    p.add_argument("--captured", help="Date the numbers were read, YYYY-MM-DD (default: today)")
    p.add_argument("--posted-date", dest="posted_date", help="Only used if the post isn't already marked posted")
    for m in METRICS:
        p.add_argument(f"--{m.replace('_', '-')}", dest=m, type=float)
    p.add_argument("--notes")

    p = sub.add_parser("followers", parents=[common])
    p.add_argument("--count", required=True, type=int)
    p.add_argument("--date")
    p.add_argument("--notes")

    p = sub.add_parser("settings", parents=[common])
    p.add_argument("--days", help="Alias for --lunch-days")
    p.add_argument("--lunch-days", dest="lunch_days", help="Comma-separated, e.g. Mon,Tue,Wed,Thu,Fri,Sat,Sun")
    p.add_argument("--evening-days", dest="evening_days", help="Comma-separated, e.g. Mon,Wed,Fri,Sun")
    p.add_argument("--test-start", dest="test_start", help="Frequency test start, YYYY-MM-DD")
    p.add_argument("--test-end", dest="test_end", help="Frequency test end, YYYY-MM-DD")
    p.add_argument("--add-pillar", dest="add_pillar")
    p.add_argument("--goal", type=int, help="Follower goal")
    p.add_argument("--goal-date", dest="goal_date", help="YYYY-MM-DD")
    p.add_argument("--remove-pillar", dest="remove_pillar")

    p = sub.add_parser("review", parents=[common])
    p.add_argument("--date", help="Review as of YYYY-MM-DD (default: today)")
    p.add_argument("--limit", type=int, default=10, help="Max screenshot requests to list")

    p = sub.add_parser("report", parents=[common])
    p.add_argument("--top", type=int, default=3)

    p = sub.add_parser("patterns", parents=[common])
    return ap


def main():
    a = build_parser().parse_args()
    path = Path(a.file).expanduser()
    try:
        if not path.exists():
            raise TrackerError(f"Tracker not found at {path}. Build it: python3 execution/instagram_tracker.py")
        wb = load_workbook(path)
        check_schema(wb)
        changed, out = COMMANDS[a.command](wb, a)
        if changed:
            check_lock_file(path)
            backup(path)
            wb.save(path)
    except (TrackerError, SchemaError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print("\n".join(out))


if __name__ == "__main__":
    main()
