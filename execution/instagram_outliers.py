#!/usr/bin/env python3
"""
Instagram Outliers — the @threelittlereaders niche scan (our own Eden).
Finds reading/phonics videos that did far better than their creator's normal,
so the Format Analyst can reverse-engineer why, and the interview can turn the
pattern into something only she could post.

Modelled on Eden (eden.so, Dan Koe's creator workspace, researched 1 Nov 2026):
"outlier" = a post's views ÷ that creator's typical views. Eden's 10×/21×/28×
badges are this number. We keep the maths and the breakdown, skip the canvas,
and feed the Format Finder instead of a generic hook library.

Sources (Apify, her free plan: $5/month credit, resets monthly):
  Instagram  apify/instagram-reel-scraper (creators), apify/instagram-hashtag-scraper
  TikTok     clockworks/tiktok-scraper (creators + hashtags, with subtitles)
Never Facebook (her rule, 1 Nov 2026). Apify scrapes from its own servers with
no login, so nothing touches the @threelittlereaders account.

How a scan works (deterministic, every number printed):
  1. Active creators: their latest videos (30 the first time, to build a
     baseline; 15 after that).
  2. Hashtags: the top videos per tag, which surfaces creators we don't know.
  3. Discovery: the 3 biggest unknown creators per platform from step 2 get one
     baseline scrape. They're saved inactive; `creators --activate` keeps them.
  Before any run: a cost estimate, refused if it's over --max-usd or over the
  credit left this month. Each Apify run also carries a hard charge cap.

How `outliers` scores:
  baseline   median views of the creator's non-pinned videos from the last
             365 days, once there are at least 5 of them. Fewer → unscored.
             Videos under 3 days old are left out of everything (views unsettled).
  multiple   views ÷ baseline. ≥ --min (default 3) and posted in the last
             --days (default 120) counts.
  niche      the caption or hashtags must mention reading (NICHE); off-niche
             outliers are counted, not shown. Pinned posts are listed apart:
             the creator's own pick, any age, often an app or course promo.

Subcommands:
  scan        [--platform ig|tt|both] [--max-usd 1.5] [--dry-run]
  outliers    [--min 3] [--days 120] [--platform …] [--top 25]
  breakdown   [--top 10] [--min 3] [--pinned]   the analyst's pack: stats, caption, cover,
              transcript (TikTok subtitles), and our format list. Run it the
              same day as the scan: subtitle and cover links expire.
  creators    list the watchlist  |  --add HANDLE --platform ig|tt  |  --activate HANDLE --platform …
              |  --deactivate HANDLE --platform …

Usage:
    python3 execution/instagram_outliers.py scan --dry-run
    python3 execution/instagram_outliers.py scan
    python3 execution/instagram_outliers.py outliers
    python3 execution/instagram_outliers.py breakdown --top 10
"""

import argparse
import csv
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "instagram" / "outliers"
VIDEOS_FILE = OUT / "videos.csv"
CREATORS_FILE = OUT / "creators.csv"
SCAN_LOG = OUT / "scan_log.csv"
BREAKDOWNS = OUT / "breakdowns"

VIDEO_FIELDS = ["key", "platform", "id", "creator", "followers", "posted", "views", "likes", "comments",
                "shares", "saves", "duration", "pinned", "kind", "caption", "hashtags", "url", "cover",
                "subtitles", "found_via", "first_seen", "scanned", "status"]
CREATOR_FIELDS = ["platform", "handle", "active", "source", "added", "followers", "note"]
LOG_FIELDS = ["date", "platform", "actor", "input", "items", "usd"]

API = "https://api.apify.com/v2"
ACTORS = {"ig_creators": "apify~instagram-reel-scraper", "ig_tags": "apify~instagram-hashtag-scraper",
          "tt": "clockworks~tiktok-scraper"}
# Free-tier price per result (checked 1 Nov 2026). Only used for the estimate:
# the real charge is read back from each run and logged.
PRICE = {"ig": 0.0026, "tt": 0.0037}
PLATFORMS = {"ig": "Instagram", "tt": "TikTok"}

SEEDS = [("ig", "toddlerscanread"), ("ig", "readingroots.uk"),
         ("tt", "toddlerscanread"), ("tt", "readingroots")]
HASHTAGS = {"ig": ["phonics", "earlyreading", "teachingkidstoread"],
            "tt": ["phonics", "teachingkidstoread", "earlyreading"]}
FIRST_PULL, REFRESH_PULL, PER_TAG, DISCOVER, DISCOVER_PULL = 30, 15, 25, 3, 15
DISCOVER_MIN_VIEWS = 20000
MIN_BASELINE = 5
# A video needs a few days before its views mean anything
SETTLED = (date.today() - timedelta(days=3)).isoformat()
# On-niche = the caption or hashtags mention reading. Off-niche outliers (a big
# creator's politics, a song for an ESL class) are counted but hidden.
NICHE = (r"read|phonic|phonem|letter|sound|word|book|spell|blend|decod|alphabet|\babc|satpin|cvc|"
         r"syllab|rhym|literacy|story|stories|sight ?word|tricky|vowel|digraph")


class OutlierError(Exception):
    pass


# ---------- files ----------

def read_csv(path, fields):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [{k: r.get(k, "") for k in fields} for r in csv.DictReader(f)]


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def creators():
    rows = read_csv(CREATORS_FILE, CREATOR_FIELDS)
    if not rows:
        rows = [dict(platform=p, handle=h, active="yes", source="seed", added=date.today().isoformat(),
                     followers="", note="") for p, h in SEEDS]
        write_csv(CREATORS_FILE, CREATOR_FIELDS, rows)
    return rows


def env(name):
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


# ---------- Apify ----------

def api(method, path, token, body=None, params=None):
    url = f"{API}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise OutlierError(f"Apify {e.code} on {path}: {e.read()[:300].decode(errors='replace')}")


def credit_left(token):
    d = api("GET", "/users/me/limits", token)["data"]
    return d["limits"]["maxMonthlyUsageUsd"] - d["current"]["monthlyUsageUsd"], d["monthlyUsageCycle"]["endAt"][:10]


def run_actor(token, actor, inp, cap_usd):
    """Start a run with a hard charge cap, wait for it, return (items, usd)."""
    run = api("POST", f"/acts/{actor}/runs", token, inp, {"maxTotalChargeUsd": f"{cap_usd:.2f}"})["data"]
    while run["status"] in ("READY", "RUNNING"):
        time.sleep(8)
        run = api("GET", f"/actor-runs/{run['id']}", token)["data"]
    if run["status"] != "SUCCEEDED":
        print(f"  ⚠ {actor} ended {run['status']}: keeping whatever it returned")
    items = api("GET", f"/datasets/{run['defaultDatasetId']}/items", token, params={"clean": "true"})
    return items, float(run.get("usageTotalUsd") or 0)


# ---------- normalising ----------

def norm_ig(r, via):
    views = r.get("videoPlayCount") or r.get("videoViewCount")
    if not views or not r.get("shortCode"):
        return None  # photos and carousels have no views to compare
    return dict(platform="ig", id=r["shortCode"], creator=(r.get("ownerUsername") or "").lower(), followers="",
                posted=(r.get("timestamp") or "")[:10], views=views, likes=r.get("likesCount") or "",
                comments=r.get("commentsCount") or "", shares=r.get("sharesCount") or "", saves="", duration=round(r.get("videoDuration") or 0),
                pinned="yes" if r.get("isPinned") else "", kind="reel", caption=(r.get("caption") or "").strip(),
                hashtags=" ".join(r.get("hashtags") or []), url=r.get("url") or "", cover=r.get("displayUrl") or "",
                subtitles="", found_via=via)


def norm_tt(r, via):
    if r.get("error") or not r.get("id") or r.get("playCount") is None:
        return None
    a, v = r.get("authorMeta") or {}, r.get("videoMeta") or {}
    subs = next((s.get("downloadLink") for s in v.get("subtitleLinks") or []
                 if (s.get("language") or "").startswith("eng")), "")
    return dict(platform="tt", id=str(r["id"]), creator=(a.get("name") or "").lower(), followers=a.get("fans") or "",
                posted=(r.get("createTimeISO") or "")[:10], views=r["playCount"], likes=r.get("diggCount") or "",
                comments=r.get("commentCount") or "", shares=r.get("shareCount") or "",
                saves=r.get("collectCount") or "", duration=v.get("duration") or "",
                pinned="yes" if r.get("isPinned") else "", kind="slideshow" if r.get("isSlideshow") else "video",
                caption=(r.get("text") or "").strip(), hashtags=" ".join(h.get("name", "") for h in r.get("hashtags") or []),
                url=r.get("webVideoUrl") or "", cover=v.get("coverUrl") or "", subtitles=subs or "", found_via=via)


def hashtag_of(item):
    """Which tag a hashtag result came from: TikTok says so, Instagram only in its URL."""
    tag = item.get("searchHashtag")
    if isinstance(tag, dict) and tag.get("name"):
        return tag["name"]
    m = re.search(r"/explore/tags/([^/?]+)", item.get("inputUrl") or "")
    return m.group(1) if m else "tag"


def tt_input(profiles=None, hashtags=None, n=15):
    inp = {"resultsPerPage": n, "shouldDownloadSubtitles": True, "shouldDownloadVideos": False,
           "shouldDownloadCovers": False}
    if profiles:
        inp.update(profiles=profiles, profileSorting="latest", excludePinnedPosts=False)
    if hashtags:
        inp["hashtags"] = hashtags
    return inp


# ---------- scan ----------

def scan_jobs(platform, active, stored):
    """The runs a scan will make, before discovery: (label, actor, input, expected items)."""
    have = {}
    for v in stored:
        have[(v["platform"], v["creator"])] = have.get((v["platform"], v["creator"]), 0) + 1
    jobs = []
    for p in (["ig", "tt"] if platform == "both" else [platform]):
        handles = [c["handle"] for c in active if c["platform"] == p]
        for n in (FIRST_PULL, REFRESH_PULL):
            group = [h for h in handles if (have.get((p, h.lower()), 0) < 10) == (n == FIRST_PULL)]
            if not group:
                continue
            if p == "ig":
                jobs.append((p, f"creators ({n} each)", ACTORS["ig_creators"], {"username": group, "resultsLimit": n},
                             n * len(group), "creator"))
            else:
                jobs.append((p, f"creators ({n} each)", ACTORS["tt"], tt_input(profiles=group, n=n), n * len(group), "creator"))
        tags = HASHTAGS[p]
        if p == "ig":
            jobs.append((p, "hashtags", ACTORS["ig_tags"], {"hashtags": tags, "resultsType": "reels", "resultsLimit": PER_TAG},
                         PER_TAG * len(tags), "hashtag"))
        else:
            jobs.append((p, "hashtags", ACTORS["tt"], tt_input(hashtags=tags, n=PER_TAG), PER_TAG * len(tags), "hashtag"))
    return jobs


def estimate(jobs, platform):
    usd = sum(job[4] * PRICE[job[0]] for job in jobs)
    disc = sum(DISCOVER * DISCOVER_PULL * PRICE[p] for p in (["ig", "tt"] if platform == "both" else [platform]))
    return usd, disc


def merge(stored, found):
    today = date.today().isoformat()
    by_key = {v["key"]: v for v in stored}
    new = 0
    for f in found:
        key = f"{f['platform']}:{f['id']}"
        if key in by_key:
            old = by_key[key]
            for k in ("views", "likes", "comments", "shares", "saves", "followers", "cover", "subtitles", "pinned"):
                if f[k] not in ("", None):
                    old[k] = f[k]
            old["scanned"] = today
        else:
            by_key[key] = dict(f, key=key, first_seen=today, scanned=today, status="")
            new += 1
    return list(by_key.values()), new


def cmd_scan(a):
    token = env("APIFY_API_TOKEN")
    if not token:
        raise OutlierError("No APIFY_API_TOKEN in .env.")
    roster, stored = creators(), read_csv(VIDEOS_FILE, VIDEO_FIELDS)
    active = [c for c in roster if c["active"] == "yes"]
    jobs = scan_jobs(a.platform, active, stored)
    base, disc = estimate(jobs, a.platform)
    left, resets = credit_left(token)
    print(f"Scan plan ({', '.join(PLATFORMS[p] for p in (['ig', 'tt'] if a.platform == 'both' else [a.platform]))}):")
    for p, label, actor, inp, n, via in jobs:
        what = inp.get("username") or inp.get("profiles") or inp.get("hashtags")
        print(f"  {PLATFORMS[p]:<9} {label:<20} ~{n:>3} results  ~${n * PRICE[p]:.2f}   {', '.join(what)}")
    print(f"  + discovery: up to {DISCOVER} new creators × {DISCOVER_PULL} per platform, ~${disc:.2f}")
    total = base + disc
    print(f"Estimate: ~${total:.2f}   ·   credit left this month: ${left:.2f} (resets {resets})")
    if total > a.max_usd:
        raise OutlierError(f"Estimate ${total:.2f} is over --max-usd {a.max_usd}. Nothing run.")
    if total > left:
        raise OutlierError("Estimate is over the credit left this month. Nothing run.")
    if a.dry_run:
        print("Dry run: nothing scraped.")
        return

    log, found, spent = read_csv(SCAN_LOG, LOG_FIELDS), [], 0.0
    norm = {"ig": norm_ig, "tt": norm_tt}

    def run(p, label, actor, inp, n, via):
        nonlocal spent
        print(f"→ {PLATFORMS[p]} {label}…", flush=True)
        # Apify won't take a per-run cap under $0.50, so this only stops a runaway run;
        # the estimate check above is what keeps a scan inside the month's credit
        items, usd = run_actor(token, actor, inp, max(0.5, n * PRICE[p] * 1.3))
        spent += usd
        for it in items:
            row = norm[p](it, f"#{hashtag_of(it)}" if via == "hashtag" else via)
            if row:
                found.append(row)
        log.append(dict(date=date.today().isoformat(), platform=p, actor=actor, input=label, items=len(items), usd=f"{usd:.3f}"))
        print(f"  {len(items)} results, ${usd:.3f}")

    try:
        for job in jobs:
            run(*job)

        # discovery: the biggest creators the hashtags surfaced that aren't on the watchlist
        known = {(c["platform"], c["handle"].lower()) for c in roster}
        for p in (["ig", "tt"] if a.platform == "both" else [a.platform]):
            best = {}
            for f in found:
                if f["platform"] == p and f["found_via"].startswith("#") and (p, f["creator"]) not in known and f["creator"]:
                    best[f["creator"]] = max(best.get(f["creator"], 0), int(f["views"]))
            picks = [h for h, v in sorted(best.items(), key=lambda x: -x[1]) if v >= DISCOVER_MIN_VIEWS][:DISCOVER]
            if not picks:
                continue
            inp = {"username": picks, "resultsLimit": DISCOVER_PULL} if p == "ig" else tt_input(profiles=picks, n=DISCOVER_PULL)
            run(p, "discovered creators", ACTORS["ig_creators"] if p == "ig" else ACTORS["tt"], inp,
                DISCOVER_PULL * len(picks), "discovered")
            for h in picks:
                roster.append(dict(platform=p, handle=h, active="no", source="discovered", added=date.today().isoformat(),
                                   followers="", note=f"top hashtag video {best[h]:,} views"))
    finally:
        # save whatever came back, even if a later run failed: those results are already paid for
        save(stored, found, roster, log)
        print(f"Spent ${spent:.2f}.")
    print("Next: outliers, then breakdown the same day (subtitle and cover links expire).")


def save(stored, found, roster, log):
    # followers on the roster, from the freshest TikTok rows
    for c in roster:
        fol = [f["followers"] for f in found if f["platform"] == c["platform"] and f["creator"] == c["handle"].lower() and f["followers"]]
        if fol:
            c["followers"] = fol[-1]
    merged, new = merge(stored, found)
    write_csv(VIDEOS_FILE, VIDEO_FIELDS, merged)
    write_csv(CREATORS_FILE, CREATOR_FIELDS, roster)
    write_csv(SCAN_LOG, LOG_FIELDS, log)
    print(f"\n✓ {len(found)} videos ({new} new), {len(merged)} stored.")


# ---------- outliers ----------

def baselines(videos):
    cutoff = (date.today() - timedelta(days=365)).isoformat()
    groups = {}
    for v in videos:
        if not v["pinned"] and cutoff <= v["posted"] <= SETTLED:
            groups.setdefault((v["platform"], v["creator"]), []).append(int(v["views"]))
    return {k: (statistics.median(vs), len(vs)) for k, vs in groups.items() if len(vs) >= MIN_BASELINE}


def on_niche(v):
    return bool(re.search(NICHE, f"{v['caption']} {v['hashtags']}", re.I))


def score(videos, min_x, days, platform=None):
    """Every scored video at or over min_x, flagged pinned / off-niche; recent and settled only, pinned at any age."""
    base, cutoff = baselines(videos), (date.today() - timedelta(days=days)).isoformat()
    out = []
    for v in videos:
        if platform and v["platform"] != platform:
            continue
        b = base.get((v["platform"], v["creator"]))
        if not b or b[0] <= 0 or v["posted"] > SETTLED:
            continue
        x = int(v["views"]) / b[0]
        if x >= min_x and (v["posted"] >= cutoff or v["pinned"]):
            out.append(dict(v, multiple=x, baseline=b[0], base_n=b[1], niche=on_niche(v)))
    return sorted(out, key=lambda r: -r["multiple"]), base


def short(text, n):
    text = re.sub(r"\s+", " ", text or "")
    return text if len(text) <= n else text[: n - 1] + "…"


def show(i, r):
    print(f"{i:>2}. {r['multiple']:>5.1f}×  {int(r['views']):>10,}  {PLATFORMS[r['platform']]:<9} @{r['creator']:<22} "
          f"{r['posted']}  {r['duration'] or '?'}s")
    print(f"      {short(r['caption'], 110)}")
    print(f"      {r['url']}   (baseline {int(r['baseline']):,} over {r['base_n']}){'  · ' + r['status'] if r['status'] else ''}")


def cmd_outliers(a):
    videos = read_csv(VIDEOS_FILE, VIDEO_FIELDS)
    if not videos:
        raise OutlierError("No videos yet: run scan first.")
    rows, base = score(videos, a.min, a.days, None if a.platform == "both" else a.platform)
    recent = [r for r in rows if r["niche"] and not r["pinned"]]
    pinned = [r for r in rows if r["niche"] and r["pinned"]]
    off = [r for r in rows if not r["niche"]]
    creators_seen = {(v["platform"], v["creator"]) for v in videos}
    print(f"{len(videos)} videos from {len(creators_seen)} creators; {len(base)} have a baseline (≥{MIN_BASELINE} settled videos).")
    print(f"Outliers ≥{a.min}× posted in the last {a.days} days, on reading/phonics: {len(recent)}\n")
    for i, r in enumerate(recent[: a.top], 1):
        show(i, r)
    if pinned:
        print(f"\n📌 Pinned by the creator (their own pick, any age): {len(pinned)}")
        for i, r in enumerate(pinned[:5], 1):
            show(i, r)
    if off:
        print(f"\nHidden as off-niche (no reading cue in caption or hashtags): {len(off)}, from "
              + ", ".join(sorted({f"@{r['creator']}" for r in off})))
    unscored = sorted({c for c in creators_seen if c not in base})
    if unscored:
        print(f"\nUnscored (under {MIN_BASELINE} settled videos): {len(unscored)} creators, mostly one-off hashtag finds.")


# ---------- breakdown pack ----------

def fetch(url, dest):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            dest.write_bytes(r.read())
        return True
    except Exception:
        return False


def vtt_text(raw):
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line == "WEBVTT" or "-->" in line or line.isdigit():
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if not lines or lines[-1] != line:
            lines.append(line)
    return " ".join(lines)


def our_formats():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from instagram_formats import FORMATS
        return [(fid, f["name"], f["family"]) for fid, f in FORMATS.items()]
    except Exception:
        return []


def cmd_breakdown(a):
    videos = read_csv(VIDEOS_FILE, VIDEO_FIELDS)
    rows, _ = score(videos, a.min, a.days)
    picks = [r for r in rows if r["niche"] and not r["status"] and (a.pinned or not r["pinned"])][: a.top]
    if not picks:
        print("Nothing new to break down (every outlier is already packed). Run a scan for fresh ones.")
        return
    folder = BREAKDOWNS / date.today().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    pack = [f"# Outlier breakdown pack · {date.today().isoformat()}", "",
            "For the Format Analyst (`.claude/agents/ig-format-analyst.md`). One section per video: the numbers, "
            "the caption, the cover image (Read it), and the transcript where TikTok had subtitles. "
            "Write each breakdown under its `### Breakdown` line.", ""]
    for i, r in enumerate(picks, 1):
        slug = f"{i:02d}_{r['platform']}_{re.sub(r'[^a-z0-9]+', '-', r['creator'])}"
        cover = folder / f"{slug}.jpg"
        has_cover = bool(r["cover"]) and fetch(r["cover"], cover)
        transcript = ""
        if r["subtitles"]:
            sub = folder / f"{slug}.vtt"
            if fetch(r["subtitles"], sub):
                transcript = vtt_text(sub.read_text(errors="replace"))
        stats = [f"{int(r['views']):,} views", f"{r['multiple']:.1f}× @{r['creator']}'s median of {int(r['baseline']):,}"]
        for k, label in (("likes", "likes"), ("comments", "comments"), ("shares", "shares"), ("saves", "saves")):
            if r[k]:
                stats.append(f"{int(r[k]):,} {label}")
        pack += [f"## {i}. @{r['creator']} · {PLATFORMS[r['platform']]} · {r['multiple']:.1f}×", "",
                 f"- **Link:** {r['url']}", f"- **Posted:** {r['posted']}{' (pinned)' if r['pinned'] else ''} · "
                 f"{r['duration'] or '?'}s · {r['kind']}", f"- **Numbers:** {' · '.join(stats)}",
                 f"- **Cover:** {cover.relative_to(ROOT) if has_cover else 'not available (link expired: rescan)'}",
                 f"- **Hashtags:** {r['hashtags'] or '—'}", "", "**Caption:**", "", "> " + (r["caption"] or "—").replace("\n", "\n> "), "",
                 "**Transcript:**", "", ("> " + short(transcript, 3000)) if transcript else
                 "_none (Instagram, or no subtitles): work from the cover, caption and numbers_", "",
                 "### Breakdown", "", "_(analyst)_", ""]
        r_store = next(v for v in videos if v["key"] == r["key"])
        r_store["status"] = f"packed {date.today().isoformat()}"
    fmts = our_formats()
    if fmts:
        pack += ["---", "", "## Our formats (map each breakdown to one, or propose a new one)", ""]
        pack += [f"- `{fid}`: {name} ({fam})" for fid, name, fam in fmts]
    (folder / "pack.md").write_text("\n".join(pack) + "\n", encoding="utf-8")
    write_csv(VIDEOS_FILE, VIDEO_FIELDS, videos)
    print(f"✓ {len(picks)} outliers packed → {(folder / 'pack.md').relative_to(ROOT)}")
    missing = sum(1 for r in picks if not r["subtitles"])
    if missing:
        print(f"  {missing} without a transcript (Instagram has no subtitles): cover + caption only.")


# ---------- creators ----------

def cmd_creators(a):
    roster = creators()
    if a.add or a.activate or a.deactivate:
        handle = (a.add or a.activate or a.deactivate).lstrip("@").lower()
        if not a.platform or a.platform == "both":
            raise OutlierError("Say which platform: --platform ig or tt.")
        match = [c for c in roster if c["platform"] == a.platform and c["handle"].lower() == handle]
        if a.add:
            if match:
                match[0]["active"] = "yes"
            else:
                roster.append(dict(platform=a.platform, handle=handle, active="yes", source="added",
                                   added=date.today().isoformat(), followers="", note=a.note or ""))
        elif not match:
            raise OutlierError(f"@{handle} isn't on the {PLATFORMS[a.platform]} watchlist.")
        else:
            match[0]["active"] = "yes" if a.activate else "no"
        write_csv(CREATORS_FILE, CREATOR_FIELDS, roster)
        print(f"✓ @{handle} ({PLATFORMS[a.platform]}) {'active' if not a.deactivate else 'inactive'}")
    for c in sorted(roster, key=lambda c: (c["platform"], c["active"] != "yes", c["handle"])):
        fol = f"{int(c['followers']):,}" if str(c["followers"]).isdigit() else "—"
        print(f"  {'●' if c['active'] == 'yes' else '○'} {PLATFORMS[c['platform']]:<9} @{c['handle']:<24} {fol:>10}  "
              f"{c['source']} {c['added']}  {c['note']}")


def main():
    ap = argparse.ArgumentParser(description="Niche outlier scan for @threelittlereaders (Instagram + TikTok, never Facebook).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan")
    p.add_argument("--platform", choices=["ig", "tt", "both"], default="both")
    p.add_argument("--max-usd", type=float, default=1.5)
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("outliers")
    p.add_argument("--min", type=float, default=3)
    p.add_argument("--days", type=int, default=120)
    p.add_argument("--platform", choices=["ig", "tt", "both"], default="both")
    p.add_argument("--top", type=int, default=25)
    p = sub.add_parser("breakdown")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--min", type=float, default=3)
    p.add_argument("--days", type=int, default=120)
    p.add_argument("--pinned", action="store_true", help="include pinned posts")
    p = sub.add_parser("creators")
    p.add_argument("--add")
    p.add_argument("--activate")
    p.add_argument("--deactivate")
    p.add_argument("--platform", choices=["ig", "tt"])
    p.add_argument("--note")
    a = ap.parse_args()
    try:
        {"scan": cmd_scan, "outliers": cmd_outliers, "breakdown": cmd_breakdown, "creators": cmd_creators}[a.cmd](a)
    except OutlierError as e:
        print(f"✗ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
