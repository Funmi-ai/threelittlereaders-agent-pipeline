#!/usr/bin/env python3
"""
Instagram Signals — the mums' own words, logged from the ChatGPT watch.

The watch runs in ChatGPT and ends every report with a "FOR CLAUDE" block in a
fixed line format (directives/threelittlereaders/watch_signals.md). She copies
only the lines worth keeping; `add` reads them (from the clipboard by default),
so logging costs no model tokens at all. Raw reports are never stored here.

Where the signals go:
  - instagram_post.py brief: hooks / copy / researcher packs get the recent
    phrases and hook seeds ("her words right now").
  - Sunday review: `themes` shows which fears repeat; a theme seen in 2+ reports
    or 3+ signals is ready to promote into Sally §6 or the community profile.

Subcommands:
  add       log SIGNAL / HOOK / IDEA lines (clipboard, --file, or piped stdin)
  list      show logged lines (--kind signal|hook|idea, --who sally|wider, --days N)
  themes    fear/want tags ranked, with ★ on themes ready to promote
  promote   mark a tag's signals as promoted (--tag behind --to sally|community)
  use       mark a hook seed or idea as used (--id SIG-004 --post IG-041)

Usage:
    python3 execution/instagram_signals.py add              # reads the clipboard
    python3 execution/instagram_signals.py add --file block.txt
    python3 execution/instagram_signals.py themes
"""

import argparse
import csv
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

SIGNALS_FILE = Path(__file__).resolve().parent.parent / "outputs" / "instagram" / "signals" / "signals.csv"
FIELDS = ["id", "logged", "kind", "who", "stage", "tag", "text", "underneath", "source", "seen", "status", "notes"]
KINDS = {"SIGNAL": "signal", "HOOK": "hook", "IDEA": "idea"}
WHO = ["sally", "wider"]
STAGES = ["baby", "toddler", "preschool", "reception", "ks1", "mixed"]
# Fixed vocabulary so themes can be counted. Mirrors Sally's tension list
# (audience_sally_2.md §2) plus what she wants (§4). Add with care: near-duplicates split the counts.
TAGS = {
    "behind": "my child is behind",
    "comparison": "looking sideways at other kids",
    "doing-enough": "is what I can fit in enough?",
    "pushing-too-hard": "what if I push too much?",
    "wrong-method": "am I using the right phonics / scheme?",
    "wrong-order": "am I following the right sequence?",
    "needs-curriculum": "do I need a curriculum / programme?",
    "too-early": "starting too early",
    "too-late": "starting too late",
    "no-time": "no time / energy",
    "knowledge-gap": "I don't know enough to teach this",
    "play-enough": "is play really enough?",
    "child-resists": "my child won't engage",
    "school-vs-home": "school and home pulling different ways",
    "buying-stuff": "do I need to buy resources?",
    "ahead-what-next": "child is ahead, what next?",
    "want-love-of-reading": "wants a child who loves reading",
    "want-independence": "wants a child who can work things out",
    "want-practical-how": "wants exactly what to do tomorrow",
}
PROMOTE_REPORTS, PROMOTE_SIGNALS = 2, 3  # seen in 2+ separate reports, or 3+ signals


class SignalError(Exception):
    pass


# --------------------------------------------------------------------------
def load():
    if not SIGNALS_FILE.exists():
        return []
    with SIGNALS_FILE.open(newline="") as f:
        return list(csv.DictReader(f))


def save(rows):
    SIGNALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SIGNALS_FILE.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def as_date(s):
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def parse_block(text):
    """'SIGNAL | who: sally | tag: behind | phrase: "…" | …' → dicts. Other lines are ignored,
    so pasting a whole report by mistake only picks up the block."""
    out = []
    for line in text.splitlines():
        line = line.strip().lstrip("-•* ").strip()
        head = line.split("|", 1)[0].strip().upper()
        if head not in KINDS or "|" not in line:
            continue
        rec = {"kind": KINDS[head]}
        for part in line.split("|")[1:]:
            if ":" in part:
                k, v = part.split(":", 1)
                v = v.strip()
                if len(v) > 1 and v[0] in '"“' and v[-1] in '"”':  # only strip quotes that wrap the whole value
                    v = v[1:-1].strip()
                rec[k.strip().lower()] = v
        rec["text"] = rec.pop("phrase", None) or rec.pop("text", "")
        rec["who"] = (rec.pop("for", None) or rec.get("who") or "").lower()
        out.append(rec)
    return out


def read_input(a):
    if a.file:
        return Path(a.file).read_text()
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return subprocess.run(["pbpaste"], capture_output=True, text=True).stdout


# --------------------------------------------------------------------------
def cmd_add(a):
    from instagram_hooks import voice_issues
    rows = load()
    seen_text = {r["text"].lower() for r in rows}
    nums = [int(r["id"][4:]) for r in rows if r["id"].startswith("SIG-")]
    n = max(nums, default=0)
    added, out = [], []
    for rec in parse_block(read_input(a)):
        warn = []
        if not rec["text"]:
            continue
        if rec["text"].lower() in seen_text:
            out.append(f"  = already logged: {rec['text'][:70]}")
            continue
        if rec["who"] not in WHO:
            warn.append(f"who '{rec['who']}' (use {'/'.join(WHO)})")
        if rec["kind"] == "signal":
            if rec.get("tag") not in TAGS:
                warn.append(f"tag '{rec.get('tag')}' isn't in the list (see `themes --tags`)")
            if rec.get("stage") and rec["stage"] not in STAGES:
                warn.append(f"stage '{rec['stage']}'")
            if not str(rec.get("source", "")).lower().startswith(("http", "our story", "our comments", "our dms", "our threads")):
                warn.append("no source link (can't be checked)")
        if rec["kind"] == "hook":
            warn += voice_issues(rec["text"])  # the watch's hooks are raw material, not finished hooks
        n += 1
        row = {f: "" for f in FIELDS}
        row.update({k: v for k, v in rec.items() if k in FIELDS})
        row.update(id=f"SIG-{n:03d}", logged=date.today().isoformat(), status="new",
                   notes="; ".join(warn))
        rows.append(row)
        seen_text.add(rec["text"].lower())
        added.append(row)
        flag = f"  ⚠ {'; '.join(warn)}" if warn else ""
        out.append(f"  + {row['id']} {row['kind']:6} {row['who'] or '?':5} {row.get('tag') or '':16} {row['text'][:60]}{flag}")
    if not added and not out:
        raise SignalError("No SIGNAL / HOOK / IDEA lines found. Copy the lines from the FOR CLAUDE block first.")
    if added:
        save(rows)
    return [f"Logged {len(added)} line(s) to {SIGNALS_FILE.name}"] + out


def recent(kind=None, who=None, days=None, status=None, limit=None):
    rows = [r for r in load() if (not kind or r["kind"] == kind) and (not who or r["who"] == who)
            and (not status or r["status"] in status)]
    if days:
        cutoff = date.today() - timedelta(days=days)
        rows = [r for r in rows if (as_date(r["logged"]) or date.min) >= cutoff]
    rows.sort(key=lambda r: r["id"], reverse=True)
    return rows[:limit] if limit else rows


def fmt(r):
    if r["kind"] == "signal":
        bits = " · ".join(b for b in (r["tag"], r["stage"]) if b)
        return f"- \"{r['text']}\" → {r['underneath'] or '?'} [{bits}]"
    flag = f" (✗ {r['notes']})" if r["notes"] else ""
    return f"- {r['id']}: {r['text']}{flag}"


def cmd_list(a):
    rows = recent(a.kind, a.who, a.days)
    return [f"{r['id']} · {r['logged']} · {r['kind']} · {r['who']} · {r['status']}\n  {fmt(r)[2:]}" for r in rows] \
        or ["Nothing logged yet."]


def themes():
    """[(tag, signals, reports, sally, wider, latest_text, ready)] newest-first within ties."""
    by_tag = {}
    for r in load():
        if r["kind"] != "signal" or not r["tag"]:
            continue
        by_tag.setdefault(r["tag"], []).append(r)
    out = []
    for tag, rs in by_tag.items():
        reports = len({r["logged"] for r in rs})  # one paste = one report
        unpromoted = [r for r in rs if r["status"] != "promoted"]
        ready = bool(unpromoted) and (reports >= PROMOTE_REPORTS or len(rs) >= PROMOTE_SIGNALS)
        out.append((tag, len(rs), reports, sum(r["who"] == "sally" for r in rs),
                    sum(r["who"] == "wider" for r in rs), max(rs, key=lambda r: r["id"])["text"], ready))
    return sorted(out, key=lambda t: (-t[1], -t[2], t[0]))


def cmd_themes(a):
    if a.tags:
        return [f"{t:22} {d}" for t, d in TAGS.items()]
    rows = themes()
    if not rows:
        return ["No signals logged yet."]
    out = [f"{'tag':20} signals reports sally wider  latest"]
    for tag, n, reps, s, w, latest, ready in rows:
        out.append(f"{'★ ' if ready else '  '}{tag:18} {n:7} {reps:7} {s:5} {w:5}  \"{latest[:50]}\"")
    out.append(f"\n★ = ready to promote ({PROMOTE_REPORTS}+ reports or {PROMOTE_SIGNALS}+ signals): write a dated line in "
               "Sally §6 (who: sally) or audience_community.md (who: wider), then run promote.")
    return out


def cmd_promote(a):
    rows = load()
    hit = [r for r in rows if r["kind"] == "signal" and r["tag"] == a.tag and r["status"] != "promoted"]
    if not hit:
        raise SignalError(f"No unpromoted signals tagged '{a.tag}'.")
    for r in hit:
        r["status"] = "promoted"
        r["notes"] = "; ".join(x for x in (r["notes"], f"promoted to {a.to} {date.today().isoformat()}") if x)
    save(rows)
    return [f"Promoted {len(hit)} signal(s) tagged '{a.tag}' to {a.to}:"] + [fmt(r) for r in hit]


def cmd_use(a):
    rows = load()
    r = next((r for r in rows if r["id"].upper() == a.id.upper()), None)
    if not r:
        raise SignalError(f"No {a.id} in the log.")
    r["status"] = "used"
    r["notes"] = "; ".join(x for x in (r["notes"], f"used in {a.post}") if x)
    save(rows)
    return [f"{r['id']} marked used in {a.post}"]


def main():
    ap = argparse.ArgumentParser(description="Log and use the mums' words from the ChatGPT watch.")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("add")
    p.add_argument("--file", help="Read the block from a file (default: clipboard, or piped stdin)")
    p = sub.add_parser("list")
    p.add_argument("--kind", choices=sorted(KINDS.values()))
    p.add_argument("--who", choices=WHO)
    p.add_argument("--days", type=int)
    p = sub.add_parser("themes")
    p.add_argument("--tags", action="store_true", help="Print the tag vocabulary")
    p = sub.add_parser("promote")
    p.add_argument("--tag", required=True)
    p.add_argument("--to", required=True, choices=["sally", "community"])
    p = sub.add_parser("use")
    p.add_argument("--id", required=True)
    p.add_argument("--post", required=True)
    a = ap.parse_args()
    try:
        out = {"add": cmd_add, "list": cmd_list, "themes": cmd_themes, "promote": cmd_promote, "use": cmd_use}[a.command](a)
    except SignalError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print("\n".join(out))


if __name__ == "__main__":
    main()
