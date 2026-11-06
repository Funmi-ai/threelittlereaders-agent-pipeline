#!/usr/bin/env python3
"""
Instagram Post — scaffolds, briefs and checks @threelittlereaders posts so every
post moves through the team the same way and follows the current winning formula.
SOP: directives/threelittlereaders/00_pipeline.md (+ roles/*.md)

Subcommands:
  new    create the post file (the baton) from a tracker entry, with a section
         for each role: facts, research note, hooks, cover, on-screen story or
         slides, caption, design & build, QA
  brief  print one role's context pack: the test card, the post file, and only
         the excerpts of the reference files that role needs (voice rules, Sally,
         kids profile, carousel guide, hook formats, past results). Roles read
         this instead of whole files, which keeps every stage cheap.
  check  lint a post file against the rules learned so far (banned words,
         repeated words, length, emoji, overlay line length, slide length,
         hashtags, phrases reused from earlier posts) and print the checklist

The formula and thresholds below are versioned on purpose: they come from the
best-performing posts and get revised at the Sunday review. Change them here
(and bump FORMULA_VERSION + the directive) rather than ad hoc in a caption.

Usage:
    python3 execution/instagram_post.py new --id IG-019
    python3 execution/instagram_post.py brief --id IG-019 --role copy
    python3 execution/instagram_post.py check outputs/instagram/posts/week-of-2026-09-28/2026-10-02_BRIDGE_day-08-vlog-week-one-recap.md
"""

import argparse
import collections
import re
import sys
from datetime import date
from pathlib import Path

from openpyxl import load_workbook

from instagram_tracker import DEFAULT_OUTPUT, check_schema
from instagram_write import TrackerError, find_post, fmt_date

IG_DIR = DEFAULT_OUTPUT.parent
POSTS_DIR = IG_DIR / "posts"
PROJECT = Path(__file__).resolve().parent.parent
VOICE_FILE = PROJECT / "Write In Voice" / "write-in-voice.yaml"
SALLY_FILE = IG_DIR / "audience_sally_2.md"
KIDS_FILE = IG_DIR / "kids_and_approach_profile.md"
CAROUSEL_GUIDE = IG_DIR / "canva_carousel_guide.md"
COMMUNITY_FILE = IG_DIR / "audience_community.md"
IG_VOICE_FILE = IG_DIR / "voice_profile_instagram.md"  # her live-caption voice (27 Oct)
IG_TIMES_FILE = IG_DIR / "posting_times.md"  # follower active times by day (30 Oct)
WIDER_PILLARS = {"COMMUNITY", "SHARE"}  # posts meant to travel past Sally get the wider-circle profile too
CONTENT_DIRECTIVE = PROJECT / "directives" / "instagram_content.md"
# Layout: posts/week-of-<Monday>/<date>_<VIDEO PILLAR>_<slug>.md
# (one folder per Mon–Sun week to match the Sunday review; pillar in the name to browse by type)


def post_path(rec):
    from datetime import timedelta
    monday = rec["date"] - timedelta(days=rec["date"].weekday())
    pillar = (rec.get("pillar") or "UNLABELLED").upper()
    return POSTS_DIR / f"week-of-{monday:%Y-%m-%d}" / f"{rec['date']:%Y-%m-%d}_{pillar}_{slugify(rec['idea'])}.md"


def find_existing_post_file(post_id):
    """The post file actually on disk for this ID, found by its title line's
    '· IG-0xx' marker — not by the computed post_path(), which is derived from
    the tracker's current idea/pillar text and silently drifts (producing a
    *different* path than the one on disk) the moment either is edited after
    the file was created. Returns None if no file on disk carries this ID."""
    marker = f"· {post_id}".lower()
    if not POSTS_DIR.exists():
        return None
    for f in POSTS_DIR.rglob("*.md"):
        try:
            first_line = f.read_text().splitlines()[0]
        except (OSError, IndexError):
            continue
        if first_line.lower().rstrip().endswith(marker):
            return f
    return None

# --------------------------------------------------------------------------
# The formula (v1, 1 Oct 2026): beats of the best performer, "To the mum who
# only managed 5 minutes today… it still counts" (1,418 reach, 109 words).
# --------------------------------------------------------------------------
FORMULA_VERSION = "v1.2 · 27 Oct 2026 · close switched to her real patterns (❤️ or none, never 🤎), used sparingly"
FORMULA = [
    ("Direct address + reassurance in ONE line", "To the mum who… / [reassurance]. No payoff: line 1 shows under the playing video."),
    ("Tell her how to read the video", "\"This is what … looks like / can become.\""),
    ("Name the feeling", "It can feel small / like nothing is going in."),
    ("Small everyday moments (inline)", "Concrete, true details: nappies, the park, a book, blocks, a cereal box."),
    ("The mechanism", "Why it works: little moments build on each other."),
    ("Her own journey", "One line of where she's been (older boys), as proof it's possible."),
    ("Name the payoff in the video", "What the child does on screen, stated plainly and accurately."),
    ("Permission to 'you'", "Give her permission in your own words, never \"You don't need X…\" (that shape is for hooks only). Never knock schools or curricula."),
    ("Close in her words", "Fresh words, never reused. Teaching posts: a warm line and/or her follow line ('follow along…'), ❤️ at most once, or no emoji. Comedy/personal posts: end on the laugh, no lesson or follow line. Never 🤎 (it's not hers)."),
]
RULES = {
    "caption_words": (80, 140),  # best performer 109; top three 109–228
    "max_caption_laugh_emoji": 1,
    "max_heart_emoji": 1,        # ❤️ is hers, used sparingly (27 Oct)
    "max_little": 3,             # her signature word: ~2.4 per caption live; more reads as caricature
    "max_quirks": 2,             # tbh / pretty much / absolutely / Like, / inspo …: sprinkle, don't stuff
    "overlay_max_words": 7,      # default for a ~2s clip when no seconds are given
    "overlay_words_per_sec": 4,  # reading speed: a 3s line can carry ~12 words
    "cover_max_words": 10,
    "slide_max_words": 30,
    "staccato_words": 6,
    "sticker_max_chars": 22,     # Story question box prompt is cut off past this ("Ask about first sounds", 4 Oct)
    "threads_max_chars": 500,         # a sentence this short counts toward a staccato run       # ~25 is the target (canva_carousel_guide.md); flag past 30
}
DEFAULT_HASHTAGS = "#phonicsforkids #earlyliteracy #learningtoread #learningthroughplay #threelittlereaders"
REQUIRED_TAG = "#threelittlereaders"

# Mirrors the banned list in Write In Voice/write-in-voice.yaml. Keep in sync.
BANNED_WORDS = ["ship", "unlock", "forge", "game-changer", "leverage", "magic", "hack", "secret",
                "transform", "messy", "curious", "jargon", "hype", "headcount", "grunt work",
                "ai-driven", "move the needle", "actually", "nap times", "margins", "stuck", "fix",
                "actually matters", "enough"]
BANNED_PATTERNS = [
    (r"\bhere'?s what\b", "\"Here's what…\" opening"),
    (r"\bit'?s not\b[^.]{0,40}\bit'?s\b", "\"It's not X, it's Y\""),
    (r"\byou'?re not\b[^.]{0,40}\byou'?re\b", "\"You're not X, you're Y\""),
    (r"\bnot because\b[^.]{0,60}\bbut because\b", "\"Not because X but because Y\""),
    (r"\byou don'?t (need|have) to\b[^.]{0,80}\bwhen\b", "\"You don't need to X when Y\" (banned 4 Oct)"),
    (r"\bcount(s|ing|ed)?\b", "\"count\" (overused across the account)"),
    (r"\bchildren\b", "\"children\" (she says kids; \"child\" only when it means one)"),
    (r"—", "em dash (she dislikes them)"),
]
# Fine in a hook, not in caption text (her direction, 4 Oct). Checked by `check`, not by the hook lint.
CAPTION_ONLY_PATTERNS = [
    (r"\byou don'?t (need|have) (to )?\w+", "\"You don't need X…\" in the caption (hooks only)"),
]
STOPWORDS = set("""a about after again all also am an and any are as at be because been before being but by can
could did do does doing don't down during each few for from had has have having he he's her here hers him his how
i i'm i've if in into is it it's its just me more most my no nor not now of off on once only or other our out over
own same she should so some such than that that's the their them then there these they this those through to too
under until up very was we we've were what when where which while who why will with would you you're your yours
day days""".split())


STORY_TEMPLATE = f"""## On-screen story (one line per clip, ≤{RULES['overlay_max_words']} words each)
| Clip | Text on screen | ~secs |
|---|---|---|
| 1. | (who he is: "He's 19 months old.") | 2.5 |
| 2. | (what I'm doing) | 2.5 |
| 3. | (proof / payoff: the brothers, what he just did) | 2.5 |
| 4. | (one joke, e.g. "(on backing vocals)") | 2.5 |
| last | (the series: "I'm documenting all of it.") | 3 |
Model: articulate reel. "He's 5 years old. I taught him to read at home. Now I get to watch those same phonics skills play out in his spelling. I'm starting again with his brother (who's on backing vocals) and this time I'm documenting all of it.\""""
SLIDES_TEMPLATE = f"""## Slides (7–10 · ≤{RULES['slide_max_words']} words each · slide 2 must work as a cold first impression)
| # | Text on slide | Visual (photo / highlight colour) |
|---|---|---|
| 1 | (cover: opens a gap the slides close · small → swipe cue) | |
| 2 | (works on its own if Instagram re-serves the post from here) | |
| 3 | | |
| 4 | (the surprising / contrarian slide lands around here) | |
| 5 | | |
| 6 | | |
| 7 | | |
| last | (ONE ask: save, share, follow or comment · styled like the cover) | |"""


class PostError(Exception):
    pass


# --------------------------------------------------------------------------
def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower())[:40].strip("-")


def cmd_new(a):
    wb = load_workbook(DEFAULT_OUTPUT)
    check_schema(wb)
    _, rec = find_post(wb["Content Plan"], a.id)
    if not rec["date"]:
        raise PostError(f"{rec['id']} has no date yet; schedule it first.")
    path = post_path(rec)
    existing = find_existing_post_file(rec["id"])
    if existing and existing.resolve() != path.resolve() and not a.force:
        raise PostError(f"{rec['id']} already has a post file at {existing.relative_to(PROJECT)}, "
                         f"which no longer matches the path computed from the tracker's current idea/pillar "
                         f"({path.relative_to(PROJECT)}). The idea or pillar text was edited after the file was "
                         f"created. Edit the existing file directly — don't create a second one. If you really "
                         f"want a fresh file at the new path, use --force (the old one is left in place, orphaned).")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not a.force:
        raise PostError(f"{path.name} already exists (use --force to overwrite).")
    beats = "\n".join(f"{i}. **{name}**: {hint}\n   > " for i, (name, hint) in enumerate(FORMULA, 1))
    body = SLIDES_TEMPLATE if rec.get("format") == "Carousel" else STORY_TEMPLATE
    text = f"""# {rec['idea']} · {fmt_date(rec['date'])} ({(rec.get('slot') or '').lower()}) · {rec['id']}
Video: {rec.get('pillar') or '?'} · Caption angle: {rec.get('angle') or '?'}
Testing: {rec.get('testing') or '(none set)'}
Formula: {FORMULA_VERSION}
Allow repeats: 

## Facts from her (ask ALL of these in one message BEFORE drafting; never invent)
- Pillar + format (reel / carousel / still) + posting time:
- Footage, in order, + length (none → carousel / staged b-roll):
- What the child did/said (verbatim quote?), can / can't do:
- When it was filmed (affects "today"/"yesterday"):
- Her angle / feeling: what changed, what's true for her:
- Tags / credits (asked publicly?):
- Her own lines or phrasing to keep:

## Research note (Researcher · 5 lines max · skip for the fast-lane vlog)
- Closest past post + how it did:
- Format (Format Finder ★ or why not, + reel / carousel) and why:
- The one thing this tests:
- Watch out for:
- Follow reason:

## Hooks (Hook Generator · 3 options, ★ = recommended · she picks)
1.
2.
3.
Picked:

## Sally check (Sally Filter · directives/threelittlereaders/roles/sally_filter.md · full review, dated entries — append, don't overwrite)
(First entry: after Hooks, before she picks. Second entry: after Caption, before QA — compare against the first entry per the card's iterative-edit rules rather than starting over.)

## Cover
(≤{RULES['cover_max_words']} words · the grid's job: earn the tap from a profile visitor)

{body}

## Caption
{beats}

{DEFAULT_HASHTAGS}

## Repurpose (Copywriter, same pass · log what goes out: instagram_repurpose.py story / threads)
- Story: (an outtake or the reel reshare) · text: 
- Sticker (≤{RULES['sticker_max_chars']} characters, soft and warm): 
- Threads 1 (hook test: an unpicked hook as a text post): 
- Threads 2 (the caption's best paragraph, standing alone): 

## Design & build (Designer / Carousel Builder)
- Cover / Canva link:
- [ ] safe zones · [ ] reading text ≥28px · [ ] contrast pair from the guide · [ ] no front-facing faces (side angles fine) · [ ] two fonts max

## QA (Producer)
- check: 
- Approved by her: 
"""
    from instagram_write import is_fast_lane
    if is_fast_lane(rec):  # the daily vlog skips research and design, never hooks (00_pipeline.md)
        text = re.sub(r"## (Research note|Design & build) \(.*?\n(?=## )",
                      lambda m: f"## {m.group(1)}\nn/a: fast lane.\n\n", text, flags=re.S)
    path.write_text(text)
    return [f"Created {path}", "Fill the facts first, then run: python3 execution/instagram_post.py check " + str(path)]


# --------------------------------------------------------------------------
def sections(text):
    parts = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"^## (.+)", line)
        if m:
            current = m.group(1).split(" (")[0].strip().lower()
            parts[current] = []
        elif current:
            parts[current].append(line)
    return {k: "\n".join(v).strip() for k, v in parts.items()}


def caption_body(raw):
    """Caption text without notes, beat headings, quote markers or hashtags."""
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or re.match(r"^\d+\. \*\*", line) or line.startswith("("):
            continue
        lines.append(line.lstrip("> ").strip())
    return "\n".join(l for l in lines if l)


def words(text):
    return re.findall(r"[a-z][a-z'’-]*", text.lower().replace("’", "'"))


def ngrams(text, n=4):
    w = words(text)
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


# The daily vlog's fixed opener ("Day N teaching my Nmo to read") repeats on
# purpose every post (her confirmed standing exception, numbers stripped by
# words()) — never flag it as accidental reused phrasing.
# Her "Day N of teaching my Nmo to read" form (Day 7, Day 14) is the same opener.
EXEMPT_REUSED_PHRASES = {"day teaching my mo", "teaching my mo to", "my mo to read",
                         "day of teaching my", "of teaching my mo"}
# Her standing follow sign-off (her direction, 24 Oct, IG-068): it closes captions on
# purpose, in either the "Follow for more…" or "…, follow along" form (Day 14) — never flag it.
STANDING_SIGN_OFFS = ["follow for more simple ways to help your child learn to read through everyday life and play",
                      "more simple ways to help your child learn to read through everyday life and play follow along",
                      # her own live follow pattern (voice profile §6, 27 Oct): "…, so follow along if you're…"
                      "so follow along if you're",
                      "i'll be sharing more of",
                      # her standing save/send + try cues (voice profile §6, 27 Oct)
                      "save this to try with your little one",
                      "and send to a mum",
                      "so next time your little one",
                      "follow along if you'd love to help your little one",
                      # her games-series close (cup reel, 4 Nov)
                      "follow for more games that get kids reading"]
EXEMPT_REUSED_PHRASES |= {g for s in STANDING_SIGN_OFFS for g in ngrams(s)}


def cmd_check(a):
    path = Path(a.file)
    if not path.exists():
        raise PostError(f"{path} not found.")
    sec = sections(path.read_text())
    cap_key = next((k for k in sec if k.startswith("caption")), None)
    if not cap_key:
        raise PostError("No '## Caption' section found.")
    raw_caption = sec[cap_key]
    caption = caption_body(raw_caption)
    issues, ok = [], []

    # Banned words / structures (normalise curly apostrophes first so "Here’s what" is caught)
    caption = caption.replace("’", "'").replace("‘", "'")
    low = caption.lower()
    for w in BANNED_WORDS:
        if re.search(rf"\b{re.escape(w)}\b", low):
            issues.append(f"banned word: \"{w}\"")
    for pat, label in BANNED_PATTERNS + CAPTION_ONLY_PATTERNS:
        if re.search(pat, caption, flags=re.I):
            issues.append(f"avoid: {label}")
    first = caption.splitlines()[0] if caption else ""
    if first.lower().startswith("sometimes"):
        issues.append("first line starts with \"Sometimes\" (banned opener)")
    if "?" in caption.splitlines()[-1] if caption else False:
        issues.append("ends on a question: top performers ask none (untested)")

    # Repeated content words
    counts = collections.Counter(w for w in words(caption) if w not in STOPWORDS and len(w) > 3)
    # A post file can allow deliberate echoes with a line like "Allow repeats: minutes, week"
    m = re.search(r"^Allow repeats:\s*(.+)$", path.read_text(), flags=re.M | re.I)
    allowed = set(re.findall(r"[a-z']+", m.group(1).split("(")[0].lower())) if m else set()
    reps = {w: n for w, n in counts.items() if n > 1 and w not in allowed}
    if reps:
        issues.append("repeated words: " + ", ".join(f"{w}×{n}" for w, n in sorted(reps.items())))

    # Length / emoji / line register
    n = len(caption.split())
    lo, hi = RULES["caption_words"]
    (ok if lo <= n <= hi else issues).append(f"caption length {n} words (target {lo}–{hi})")
    laughs = caption.count("😂")
    if laughs > RULES["max_caption_laugh_emoji"]:
        issues.append(f"{laughs}× 😂 in caption (max {RULES['max_caption_laugh_emoji']}; humour lives in the overlay)")
    # Her real patterns, used sparingly (27 Oct): 🤎 isn't hers; ❤️ / "little" / quirks only in small doses
    if "🤎" in caption:
        issues.append("🤎 in caption: not hers (0 of her last 10 captions). Use ❤️ once, or no emoji")
    repurpose = next((sec[k] for k in sec if k.startswith("repurpose")), "")
    if "🤎" in repurpose:
        issues.append("🤎 in Repurpose (Story/sticker/Threads): not hers. Use ❤️, her 😅/🥹, or none")
    hearts = caption.count("❤")
    if hearts > RULES["max_heart_emoji"]:
        issues.append(f"{hearts}× ❤️ in caption (max {RULES['max_heart_emoji']}; she uses it sparingly)")
    littles = len(re.findall(r"\blittle\b", caption, re.I))
    if littles > RULES["max_little"]:
        issues.append(f"'little' ×{littles} (max {RULES['max_little']}; her signature word, but sparingly)")
    quirks = [q for q in (r"\btbh\b", r"\bpretty much\b", r"\babsolutely\b", r"(?:^|[.!?]\s+)Like,", r"\binspo\b",
                          r"I['’]d be lying", r"So I['’]ll take it") if re.search(q, caption, re.I)]
    if len(quirks) > RULES["max_quirks"]:
        issues.append(f"{len(quirks)} of her verbal quirks in one caption (max {RULES['max_quirks']}; sprinkle, don't stuff)")
    # Staccato: 3+ clipped sentences in a row reads like generic online copy, not her (4 Oct direction)
    sentences = [x.strip() for x in re.findall(r"[^.!?…]+[.!?…]+[\"”’']?", " ".join(caption.splitlines()))
                 if re.search(r"[a-z]", x, re.I)]  # keeps a closing quote with its sentence
    run, runs = [], []
    for x in sentences + [""]:
        if x and len(words(x)) <= RULES["staccato_words"]:
            run.append(x)
            continue
        if len(run) >= 3:
            runs.append(" ".join(run))
        run = []
    for r in runs:
        issues.append(f"staccato run (flow it into one conversational sentence): {r[:80]}")

    # Hashtags
    tags = re.findall(r"#\w+", raw_caption)
    if REQUIRED_TAG not in tags:
        issues.append(f"missing {REQUIRED_TAG}")
    if len(tags) != 5:
        issues.append(f"{len(tags)} hashtags (use the 5-tag set)")

    # Overlay and cover length
    story = next((sec[k] for k in sec if k.startswith("on-screen")), "")
    for row in story.splitlines():
        cells = [c.strip() for c in row.strip("|").split("|")]
        if len(cells) >= 2 and cells[1] and not set(cells[1]) <= set("-") and cells[1] != "Text on screen" \
                and not cells[1].startswith("("):
            wc = len([t for t in cells[1].split() if re.search(r"[A-Za-z0-9]", t)])  # emoji aren't words
            try:
                limit = int(float(cells[2]) * RULES["overlay_words_per_sec"])
            except (IndexError, ValueError):
                limit = RULES["overlay_max_words"]
            if wc > limit:
                issues.append(f"on-screen line too long for its time ({wc} words, max {limit}): {cells[1]}")
    slides = next((sec[k] for k in sec if k.startswith("slides")), "")
    for row in slides.splitlines():
        cells = [c.strip() for c in row.strip("|").split("|")]
        if len(cells) >= 2 and cells[1] and not set(cells[1]) <= set("-") and cells[1] != "Text on slide" \
                and not cells[1].startswith("("):
            wc = len([t for t in cells[1].split() if re.search(r"[A-Za-z0-9]", t)])
            if wc > RULES["slide_max_words"]:
                issues.append(f"slide {cells[0]} is {wc} words (max {RULES['slide_max_words']}; cut words, never shrink text)")
    repurpose = next((sec[k] for k in sec if k.startswith("repurpose")), "")
    for line in repurpose.splitlines():
        m = re.match(r"^- (Sticker|Threads \d)[^:]*:\s*(.+)$", line.strip())
        if not m or m.group(2).startswith("("):
            continue
        label, text = m.groups()
        visible = re.sub(r"[^\w\s'?,.!:-]", "", text).strip()  # emoji sit outside the prompt's text limit
        if label == "Sticker" and len(visible) > RULES["sticker_max_chars"]:
            issues.append(f"Story sticker is {len(visible)} characters (max {RULES['sticker_max_chars']}: the prompt gets cut off)")
        if label.startswith("Threads"):
            if len(text) > RULES["threads_max_chars"]:
                issues.append(f"{label} is {len(text)} characters (Threads allows {RULES['threads_max_chars']})")
            for w in BANNED_WORDS:
                if re.search(rf"\b{re.escape(w)}\b", text.lower()):
                    issues.append(f"{label}: banned word \"{w}\"")
    cover = sec.get("cover", "")
    cover_text = " ".join(l for l in cover.splitlines() if l and not l.startswith("("))
    if cover_text and len(cover_text.split()) > RULES["cover_max_words"]:
        issues.append(f"cover is {len(cover_text.split())} words (max {RULES['cover_max_words']})")

    # Phrases reused from earlier posts (followers notice)
    reused = collections.defaultdict(set)
    for other in POSTS_DIR.rglob("*.md"):
        if other.name.lower() == "readme.md":
            continue
        if other.resolve() == path.resolve():
            continue
        osec = sections(other.read_text())
        okey = next((k for k in osec if k.startswith("caption")), None)
        if okey:
            for g in ngrams(caption) & ngrams(caption_body(osec[okey])):
                if g in EXEMPT_REUSED_PHRASES:
                    continue
                reused[other.name].add(g)
    # Live captions too (written by instagram_sync.py): catches posts with no draft file, and her own edits (27 Oct)
    live_file = IG_DIR / "live_captions.json"
    if live_file.exists() and caption.strip():
        import json
        mine = ngrams(caption)
        for lc in json.loads(live_file.read_text()):
            theirs = ngrams(lc.get("caption", ""))
            shared = {g for g in mine & theirs if g not in EXEMPT_REUSED_PHRASES}
            if not shared or len(mine & theirs) > 0.8 * max(len(mine), 1):
                continue  # nothing shared, or it's this post's own live caption
            reused[f"LIVE {lc.get('date')} post"] |= shared
    for name, grams in reused.items():
        if not grams:
            continue
        issues.append(f"reuses phrasing from {name}: " + "; ".join(sorted(grams)[:3]))

    out = [f"Checking {path.name} against formula {FORMULA_VERSION}", ""]
    out += [f"  ✓ {o}" for o in ok]
    out += [f"  ✗ {i}" for i in issues] or ["  ✓ no rule issues"]
    out += ["", "Formula checklist (judge each by reading; a script can't):"]
    out += [f"  [ ] {i}. {name}" for i, (name, _) in enumerate(FORMULA, 1)]
    out += ["  [ ] Line 1 doesn't give away what the video/overlay is building to",
            "  [ ] Every claim about the child matches what she said (can / can't / when filmed)",
            "  [ ] Sally check: possibility not superiority; nobody's approach knocked"]
    return out, bool(issues)


# --------------------------------------------------------------------------
# Context packs (brief): each role reads its pack instead of whole files.
# Which excerpts go to which role is set here, so the role cards stay short.
# --------------------------------------------------------------------------
ROLES = ["researcher", "hooks", "copy", "design", "carousel", "sally"]


def md_sections(text):
    """[(heading, body)] for every '## ' section (heading without the '## ')."""
    out, head, buf = [], None, []
    for line in text.splitlines():
        if line.startswith("## "):
            if head is not None:
                out.append((head, "\n".join(buf).strip()))
            head, buf = line[3:].strip(), []
        elif head is not None:
            buf.append(line)
    if head is not None:
        out.append((head, "\n".join(buf).strip()))
    return out


def excerpt(path, *prefixes, drop=()):
    """The sections of a markdown file whose heading starts with any prefix.
    Paragraphs starting with anything in `drop` are cut (e.g. research notes)."""
    if not path.exists():
        return f"({path.name} not found)"
    parts = []
    for head, body in md_sections(path.read_text()):
        if any(head.lower().startswith(p.lower()) for p in prefixes):
            if drop:
                body = "\n\n".join(par for par in body.split("\n\n") if not par.startswith(drop))
            parts.append(f"### {head}\n{body}")
    return "\n\n".join(parts)


def voice_digest(learned_filter, extra=()):
    """Her hard rules plus the Instagram entries from LEARNED FROM HER EDITS,
    read live from the voice file so the digest can never go stale.
    New Instagram entries must have 'Instagram' (or 'on-screen'/'overlay') in their title."""
    if not VOICE_FILE.exists():
        return "(voice file not found)"
    text = "\n".join(l[2:] if l.startswith("  ") else l for l in VOICE_FILE.read_text().splitlines())
    secs = dict(md_sections(text))
    get = lambda prefix: next((b for h, b in secs.items() if h.startswith(prefix)), "")
    hard = get("HARD NOS").replace("---", "").strip()
    overused = get("WORDS SHE OVERUSES").replace("---", "").strip()
    entries = re.split(r"\n(?=\*\*20\d\d-)", get("LEARNED FROM HER EDITS"))
    learned = [e.strip() for e in entries[1:] if re.search(learned_filter, e.splitlines()[0], flags=re.I)]
    style = [f"### {h.title()}\n{b.replace('---', '').strip()}" for h, b in secs.items()
             if any(h.startswith(x) for x in extra)]
    return "\n\n".join(style + [f"### Hard nos\n{hard}", f"### Words she overuses (sparingly)\n{overused}",
                        "### Learned from her Instagram edits\n" + "\n\n".join(learned)])


def kids_excerpt(rec):
    """Her approach + only the child sections this post is about (all three if unclear)."""
    text = f"{rec.get('idea') or ''} {rec.get('hook') or ''}".lower()
    which = [name for name, pat in (("19-month", r"19 ?mo|19-month|vlog|youngest"),
                                    ("3-year", r"\b3 ?yo|3-year|middle"),
                                    ("5-year", r"\b5 ?yo|5-year|eldest")) if re.search(pat, text)]
    return excerpt(KIDS_FILE, "Her approach", "All three", "Footage log", *(which or ["19-month", "3-year", "5-year"]))


def pillar_rows(rec):
    rows = []
    if CONTENT_DIRECTIVE.exists():
        for line in CONTENT_DIRECTIVE.read_text().splitlines():
            for label in {rec.get("pillar"), rec.get("angle")} - {None, ""}:
                if line.startswith(f"| {label} |"):
                    rows.append(line)
    return "| Pillar | Job | Examples | Hypothesis |\n|---|---|---|---|\n" + "\n".join(rows) if rows else "(no pillar set)"


def past_results(wb, rec, limit=8):
    """The nearest evidence: past posts sharing this post's video pillar or caption angle."""
    from instagram_write import fmt_rate, load_posts
    posts = [p for p in load_posts(wb) if str(p["id"]).upper() != str(rec["id"]).upper()
             and (p["pillar"] == rec.get("pillar") or (rec.get("angle") and p["angle"] == rec.get("angle")))]
    posts.sort(key=lambda p: p["posted_date"] or date.min, reverse=True)
    if not posts:
        return "(no posted results yet for this pillar or angle)"
    lines = []
    for p in posts[:limit]:
        reach = f"{int(p['reach']):,}" if p["reach"] else "–"
        lines.append(f"- {p['id']} · {fmt_date(p['posted_date'])} · {p['format'] or '?'} · {p['pillar'] or '?'}/"
                     f"{p['angle'] or '?'} · reach {reach} · follows {fmt_rate('follow_rate', p['follow_rate'])}"
                     f" · saves {fmt_rate('save_rate', p['save_rate'])} · sends {fmt_rate('share_rate', p['share_rate'])}"
                     f" · {p['verdict'] or 'no verdict'}\n  {str(p['idea'] or '')[:90]}"
                     + (f"\n  tested: {p['testing']}" if p.get("testing") else ""))
    return "\n".join(lines)


def test_guardrails(wb):
    """The frequency test's don'ts, only while the test is running."""
    from instagram_tracker import FREQ_END_CELL
    end = wb["Settings"][FREQ_END_CELL].value
    end = end.date() if hasattr(end, "date") else end
    if not end or date.today() > end or not CONTENT_DIRECTIVE.exists():
        return ""
    m = re.search(r"\*\*While the test runs, don't:\*\*\n((?:- .+\n)+)", CONTENT_DIRECTIVE.read_text())
    return f"## Frequency test running until {fmt_date(end)}: don't\n{m.group(1).strip()}" if m else ""


def recent_hooks(wb, rec, days=14):
    """Hooks planned or used near this post's date, so formats and openers don't repeat."""
    from instagram_write import plan_rows
    lines = []
    for _, r in plan_rows(wb["Content Plan"]):
        if r["hook"] and r["date"] and rec["date"] and abs((r["date"] - rec["date"]).days) <= days \
                and r["id"] != rec["id"]:
            same = "  ← SAME DAY" if r["date"] == rec["date"] else ""
            lines.append((r["date"], f"- {fmt_date(r['date'])} · {r['id']} · {str(r['hook']).splitlines()[0][:100]}{same}"))
    return "\n".join(line for _, line in sorted(lines)) or "(none)"


def logged_hook(p):
    """The opening a viewer saw: the tracker's hook, else the post file's cover + first overlay line,
    else the caption's first line (all the sync knows for reels posted before post files existed)."""
    if p.get("hook"):
        return str(p["hook"]).splitlines()[0], ""
    for f in POSTS_DIR.rglob("*.md"):
        text = f.read_text()
        if f"· {p['id']}" in text.splitlines()[0]:
            sec = sections(text)
            cover = " ".join(l for l in sec.get("cover", "").splitlines() if l and not l.startswith("("))
            story = next((sec[k] for k in sec if k.startswith("on-screen")), "")
            first = next((c[1] for c in ([x.strip() for x in r.strip("|").split("|")] for r in story.splitlines())
                          if len(c) > 1 and c[1] and not set(c[1]) <= set("-") and c[1] != "Text on screen"
                          and not c[1].startswith("(")), "")
            if cover or first:
                return " · ".join(x for x in (f"Cover: {cover}" if cover else "", f"Overlay: {first}" if first else "") if x), ""
    return str(p["idea"] or "")[:90], " (caption line 1; no hook logged)"


def hooks_that_held(wb, rec, top=5, bottom=3):
    """Past reels ranked by skip rate (share who swiped away in the first 3 seconds: lower held better),
    split by slot because lunch vlogs reach followers and evening posts reach strangers."""
    from instagram_write import load_posts
    posts = [p for p in load_posts(wb) if p["format"] == "Reel" and p["skip_rate"] not in (None, 0)
             and p["posted_date"] and (date.today() - p["posted_date"]).days >= 2 and (p["reach"] or 0) >= 50]
    if not posts:
        return "(no reels with skip rates yet)"
    slot = rec.get("slot") or "Evening"
    out, missing = [], 0
    for label, group in ((f"Same slot ({slot.lower()})", [p for p in posts if (p.get("slot") or "Lunch") == slot]),
                         ("Other slot", [p for p in posts if (p.get("slot") or "Lunch") != slot])):
        if not group:
            continue
        group.sort(key=lambda p: p["skip_rate"])
        shown = group[:top] + [p for p in group[top:][-bottom:]]
        out.append(f"{label} · best first · median skip {sorted(g['skip_rate'] for g in group)[len(group) // 2]:.0%}")
        for i, p in enumerate(shown):
            if i == top:
                out.append("  …lost them:")
            hook, note = logged_hook(p)
            missing += bool(note)
            wt = f"{p['watch_time']:.0f}s" if p["watch_time"] else "–"
            out.append(f"  {p['skip_rate']:.0%} skip · {wt} watch · {p['id']} {p['pillar'] or '?'} · {hook}{note}")
    out.append("Skip rate is the hook's report card, but the first frame counts as much as the words. Small sample: patterns, not proof.")
    if missing:
        out.append(f"{missing} of these have no hook logged: backfill with instagram_write.py edit --id … --hook \"Cover: … · Overlay: …\"")
    return "\n".join(out)


def hook_formats(rec):
    from instagram_hooks import HOOKS
    labels = {rec.get("pillar"), rec.get("angle")} - {None, ""}
    rows = [h for h in HOOKS if not labels or labels & set(h[3])]
    out = []
    for hid, name, tpl, pillars, safe, notes in rows:
        out.append(f"- {hid} · {name} [{', '.join(pillars)}]\n  {safe or tpl}" + (f"\n  evidence: {notes}" if notes else ""))
    return "\n".join(out)


def signals_block(rec, role):
    """The mums' own words from the ChatGPT watch (instagram_signals.py), recent first.
    Wider-circle lines only for posts meant to travel past Sally."""
    from instagram_signals import fmt, recent, themes
    wider = bool({rec.get("pillar"), rec.get("angle")} & WIDER_PILLARS)
    out = []
    if role == "researcher":
        rows = themes()[:6]
        out += [f"- {'★ ' if t[6] else ''}{t[0]}: {t[1]} signals, {t[2]} reports · latest \"{t[5][:60]}\"" for t in rows]
        ideas = recent("idea", status={"new"}, limit=5)
        if ideas:
            out += ["Ideas from the watch (unused):"] + [fmt(r) for r in ideas]
    else:
        out += [fmt(r) for r in recent("signal", "sally", days=60, limit=12 if role == "hooks" else 8)]
        if wider:
            out += ["Wider circle:"] + [fmt(r) for r in recent("signal", "wider", days=60, limit=6)]
        if role == "hooks":
            seeds = recent("hook", status={"new"}, limit=6)
            if seeds:
                out += ["Hook seeds (raw material: lint and rewrite, never use as-is):"] + [fmt(r) for r in seeds]
    return "\n".join(out) or "(nothing logged yet: instagram_signals.py add)"


def formula_text():
    beats = "\n".join(f"{i}. {name}: {hint}" for i, (name, hint) in enumerate(FORMULA, 1))
    lo, hi = RULES["caption_words"]
    return (f"Formula {FORMULA_VERSION}\n{beats}\n\nCaption {lo}–{hi} words · conversational: flowing sentences in short paragraphs, short lines only for emphasis and the landing (no staccato runs) · no question to the"
            f" audience · max {RULES['max_caption_laugh_emoji']} 😂 · 5 hashtags: {DEFAULT_HASHTAGS}\n"
            f"On-screen: ~{RULES['overlay_words_per_sec']} words/sec · cover ≤{RULES['cover_max_words']} words")


def format_block(rec, role):
    """The Format Finder's ranking (researcher), or the format already picked for this
    post with its film plan (hooks, copy, carousel), so every role builds the same shape."""
    import argparse
    from contextlib import redirect_stdout
    import io
    from instagram_formats import cmd_find, plan_lines, read_log
    if role == "researcher":
        try:
            with redirect_stdout(io.StringIO()):
                lines = cmd_find(argparse.Namespace(id=rec["id"], idea=None, pillar=None, child=None,
                                                    message=None, goal=None, top=3))
        except SystemExit as e:
            return f"(finder couldn't run: {e})"
        return "\n".join(lines)
    row = next((r for r in read_log() if r["post"].upper() == str(rec["id"]).upper()), None)
    if not row:
        return "(no format logged yet: the Researcher picks one with instagram_formats.py find/log)"
    fid = row.get("shape") or row["format"]
    return "\n".join(plan_lines(fid))


def community_excerpt(rec):
    if not {rec.get("pillar"), rec.get("angle")} & WIDER_PILLARS:
        return []
    return ["## The wider circle (audience_community.md)", excerpt(COMMUNITY_FILE, "Segments", "Candidates", "Their words", "What we don't"), ""]


def cmd_brief(a):
    wb = load_workbook(DEFAULT_OUTPUT)
    check_schema(wb)
    _, rec = find_post(wb["Content Plan"], a.id)
    path = find_existing_post_file(rec["id"]) or (post_path(rec) if rec["date"] else None)
    from instagram_write import describe, is_fast_lane
    out = [f"# Brief · {a.role} · {rec['id']}" + (" · FAST LANE (daily vlog)" if is_fast_lane(rec) else ""),
           "", "## Test card", describe(rec), ""]
    if path and path.exists():
        out += [f"## Post file: {path.relative_to(PROJECT)}", path.read_text().strip(), ""]
    else:
        out += ["## Post file: not created yet → python3 execution/instagram_post.py new --id " + rec["id"], ""]
    if a.role in ("hooks", "copy", "carousel", "design") and IG_TIMES_FILE.exists():
        out += ["## When to post (state the recommended time for this post's day whenever you hand over overlay or cover text)",
                IG_TIMES_FILE.read_text().strip(), ""]

    if a.role == "researcher":
        out += ["## Format Finder (what should be shown: ★ goes in the Format line, then `log` it)",
                format_block(rec, a.role), "",
                "## Pillar jobs", pillar_rows(rec), "",
                "## Nearest evidence (same video pillar or caption angle, newest first)", past_results(wb, rec), "",
                test_guardrails(wb), "",
                "## From the watch (themes; ★ = ready to promote at the Sunday review)", signals_block(rec, a.role), "",
                "## Sally", excerpt(SALLY_FILE, "2.", "4.", "5.", "6.")]
    elif a.role == "hooks":
        out += ["## The format (Format Finder): write hooks for this shape, starting from its paired hooks",
                format_block(rec, a.role), "","## Hooks that held (skip rate = swiped away in the first 3s; lower is better)", hooks_that_held(wb, rec), "",
                "## Hook formats for this pillar/angle (instagram_hooks.py; `fill ID` lints a draft)", hook_formats(rec), "",
                "## Hooks within 14 days (no repeated format; never two 'To the mum…' the same day)",
                recent_hooks(wb, rec), "",
                "## Her words right now (from the watch: use their language, never quote anyone identifiably)",
                signals_block(rec, a.role), "",
                "## Sally", excerpt(SALLY_FILE, "2.", "5.", "6."), "",
                *community_excerpt(rec),
                "## Voice", voice_digest(r"instagram|overlay|on-screen", extra=("HER OPENINGS", "ENDINGS"))]
    elif a.role == "copy":
        out += ["## The format (Format Finder): the on-screen story follows these beats", format_block(rec, a.role), "","## Caption formula", formula_text(), "",
                "## The kids (accuracy: what they can and can't do)", kids_excerpt(rec), "",
                "## Her words right now (from the watch: use their language, never quote anyone identifiably)",
                signals_block(rec, a.role), "",
                "## Sally", excerpt(SALLY_FILE, "2.", "3.", "5.", "6."), "",
                *community_excerpt(rec),
                "## Her live voice (from her last 10 captions, 27 Oct). Use her patterns SPARINGLY: one or two per caption, never a caricature",
                IG_VOICE_FILE.read_text().strip() if IG_VOICE_FILE.exists() else "(voice profile not found)", "",
                "## Voice", voice_digest(r"instagram|on-screen|overlay|day \d|reels|montage",
                                       extra=("HER ACTUAL RHYTHM", "REGISTER", "PARENTHETICAL", "ANALOGIES", "ENDINGS",
                                              "VOICE CALIBRATION"))]
    elif a.role == "sally":
        out += ["## Sally, in full — fidelity matters, read all of it, not a summary",
                SALLY_FILE.read_text().strip() if SALLY_FILE.exists() else "(sally file not found)", "",
                "## Her words right now (from the watch: what real Sallys are actually saying)",
                signals_block(rec, a.role)]
    elif a.role == "design":
        out += ["## Carousel & cover rules", excerpt(CAROUSEL_GUIDE, "Canvas", "Type sizes", "Fonts", "Colour and contrast",
                                                    "House cover style", drop=("**Why",)), ""]
    elif a.role == "carousel":
        out += ["## The format (Format Finder)", format_block(rec, a.role), "","## Build rules", excerpt(CAROUSEL_GUIDE, "Canvas", "Type sizes", "Structure", "2026 nuances",
                                          drop=("Sources:",)), "",
                "## Palette (Designer owns the full rules)",
                excerpt(CAROUSEL_GUIDE, "Colour and contrast", drop=("**Why",))]
    return [l for l in out if l is not None]


def main():
    ap = argparse.ArgumentParser(description="Scaffold and check Instagram post copy.")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("new")
    p.add_argument("--id", required=True)
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("brief")
    p.add_argument("--id", required=True)
    p.add_argument("--role", required=True, choices=ROLES)
    p = sub.add_parser("check")
    p.add_argument("file")
    a = ap.parse_args()
    try:
        if a.command == "new":
            print("\n".join(cmd_new(a)))
        elif a.command == "brief":
            print("\n".join(cmd_brief(a)))
        else:
            out, has_issues = cmd_check(a)
            print("\n".join(out))
            sys.exit(1 if has_issues else 0)
    except (PostError, TrackerError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
