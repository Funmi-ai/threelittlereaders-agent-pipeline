#!/usr/bin/env python3
"""
Instagram Hooks — the user's viral hook formats (verbatim, 3 Oct 2026), with
pillar fit, voice-rule flags, voice-safe variants and evidence from
@threelittlereaders' own posts. Used by the Hook Generator role
(directives/threelittlereaders/roles/hook_generator.md) and `instagram_post.py brief --role hooks`.

Her originals are never edited here. Where a format clashes with the voice file
(Write In Voice/write-in-voice.yaml: "actually", "Here's what…", a "Sometimes"
opener, "If your X then Y" conditionals), `voice_safe` holds a version that
keeps the mechanic but fits her voice. Use whichever she prefers.

Subcommands:
  list   [--pillar PROVE]      formats, optionally only those suited to a pillar
  show   ID                    one format in full (original, voice-safe, notes)
  fill   ID "words" "words"…   slot words into the blanks in order, then lint
  lint   "hook text"           check any hook against the voice rules

Usage:
    python3 execution/instagram_hooks.py list --pillar RELATE
    python3 execution/instagram_hooks.py show nobody-warned-me
    python3 execution/instagram_hooks.py fill direct-reassurance "mum" "wonders" "if a few minutes a day is enough"
"""

import argparse
import re
import sys

from instagram_post import BANNED_PATTERNS, BANNED_WORDS

PILLARS = ["RELATE", "START", "BRIDGE", "PROVE", "SHARE", "TEACH", "COMMUNITY"]

# (id, name, original template, pillars, voice_safe or None, notes/evidence)
HOOKS = [
    ("and-to-think", "Transformation / “And to think…”", "And to think I was ___ [timeframe] ago, and now ___.",
     ["PROVE", "BRIDGE"], None, "Banked for the Day 15 recap: \"And to think he's the one I expected to be least interested…\"."),
    ("recommendation-list", "Recommendation list", "The [number] ___ I’d recommend to anyone who ___.",
     ["TEACH", "COMMUNITY"], None, ""),
    ("dear-algorithm", "Dear Algorithm", "Dear Algorithm, please bring me the ___ who ___.",
     ["COMMUNITY", "RELATE"], None, "Audience-calling hook: name Sally precisely (mums of 2–7s who want to help but worry they don't know enough)."),
    ("weird-silly", "Weird / silly things I do", "[Number] weird/silly things I do as a ___ that ___.",
     ["RELATE", "SHARE"], None, ""),
    ("experience-authority", "Experience-led authority", "As a ___, here are the [number] ___ I ___.",
     ["TEACH"], "As a ___, these are the [number] ___ I ___.", "Keep it 'a few steps ahead', never expert (Sally brief)."),
    ("you-dont-need", "“You don’t need…”", "You don’t need ___ to ___.",
     ["TEACH", "RELATE"], None, "The brand promise in hook form. Don't stack it 4× in one caption (she cut that)."),
    ("no-longer-embarrassed", "No-longer-embarrassed confession", "I’m a [age]-year-old ___ who’s no longer embarrassed to admit that ___.",
     ["RELATE"], None, "Her 'shameless era' energy. The 'winging it' confession (RELATE) had the lowest skip rate (16%)."),
    ("nobody-warned-me", "Nobody warned me", "Nobody warned me that ___.",
     ["SHARE", "RELATE"], None, "Planned: 14 Oct SHARE reel (spelling to her husband)."),
    ("unexpected-consequences", "Unexpected consequences", "Unexpected consequence(s) of ___: ___.",
     ["SHARE"], None, ""),
    ("proof", "Proof", "Proof you can ___ without ___.",
     ["PROVE", "TEACH"], None, "Show possibility, not superiority."),
    ("i-thought-i-needed", "“I thought I needed…”", "I thought I needed to ___ to ___. Turns out, ___.",
     ["RELATE", "TEACH"], None, "Dismantles Perfect Teaching Mum from her own experience."),
    ("experiment-results", "Experiment / results", "I spent [timeframe] ___ . Here’s what actually happened.",
     ["START", "PROVE"], "I spent [timeframe] ___. This is what happened.", "Voice: drop 'Here's what' and 'actually'."),
    ("what-can-open-loop", "“What can…” open loop", "What can ___ actually ___ in [timeframe]?",
     ["START", "PROVE"], "What can ___ ___ in [timeframe]?", "Used on Day 8 (her version). Curiosity question the video answers. Instruction-style questions held worst."),
    ("before-after", "Before → after", "[Timeframe] ago, ___ . Now ___.",
     ["PROVE", "BRIDGE", "START"], None, "The three boys are a natural ladder (19mo → 3yo → 5yo)."),
    ("heres-what-stuck", "“Here’s what stuck”", "I’ve been ___ for [timeframe]. Here’s what actually stuck.",
     ["START", "BRIDGE"], "I’ve been ___ for [timeframe]. This is what stuck.", "Voice: 'Here's what' + 'actually' banned. Day 8 cover used '…what stuck?'."),
    ("contradiction", "Contradiction", "I didn’t ___, but ___.",
     ["RELATE", "PROVE"], None, ""),
    ("wasnt-even", "“I wasn’t even…” surprise", "I wasn’t even ___, then ___.",
     ["RELATE", "PROVE"], None, "Fits the 19mo story: the most resistant of the three, yet engaging."),
    ("expectation-reality", "Expectation vs reality", "I expected ___ . Instead, ___.",
     ["RELATE", "START"], None, "Day 7 shape: spotting R everywhere, but not in a book."),
    ("did-any-work", "“Did any of it work?”", "I spent [timeframe] ___ . Did any of it actually ___?",
     ["START", "PROVE"], "I spent [timeframe] ___. Did any of it ___?", "Voice: drop 'actually'."),
    ("think-you-need", "“Think you need…” challenge", "Think you need ___ to ___? ___.",
     ["TEACH", "RELATE"], None, ""),
    ("downside-of", "“The downside of…”", "The downside of ___: ___.",
     ["SHARE"], None, ""),
    ("pov", "POV", "POV: ___ finally ___.",
     ["SHARE", "PROVE"], None, ""),
    ("can-no-longer", "Things I can no longer do", "Things I can no longer ___ now that ___.",
     ["SHARE"], None, "Pairs with 'Nobody warned me' (spelling things out in front of the 5yo)."),
    ("problem-with", "“The problem with…”", "The problem with ___ is eventually ___.",
     ["SHARE"], None, ""),
    ("things-i-dont-do", "“Things I don’t do…”", "Things I don’t do when ___: ___.",
     ["RELATE", "TEACH"], None, "Anti-Perfect-Teaching-Mum list. Never knock schools or curricula."),
    ("direct-reassurance", "Direct-to-person reassurance", "To the ___ who thinks/worries/wonders ___…",
     ["RELATE", "PROVE", "BRIDGE"], "To the ___ who [thinks / worries / wonders] ___…",
     "BEST PERFORMER: 'To the mum who only managed 5 minutes today… it still counts' (1,418 reach, 44% visitor→follow). Pair with a reassurance in the same line. Don't run two on the same day."),
    ("if-you-think", "“If you think…”", "If you think ___, watch this.",
     ["PROVE"], "Think ___? Watch this.", "Voice: avoid 'If you…' conditionals. 'If you're a mum who…' openers underperformed twice (221, 145)."),
    ("im-not-but", "“I’m not…” + proof", "I’m not ___ . But ___.",
     ["RELATE", "PROVE"], None, "e.g. 'I'm not a phonics expert. But…' (true, and her winging-it story)."),
    ("timeframe-input-result", "Specific timeframe + minimal input + result", "[Timeframe]. [Small amount of effort/input]. Here’s ___.",
     ["PROVE", "START"], "[Timeframe]. [Small amount of effort/input]. This is ___.", "Voice: 'Here's' opener-style banned."),
    ("it-started-with", "“It started with…” progression", "It started with ___ . Now ___.",
     ["BRIDGE", "PROVE"], None, ""),
    ("one-day", "“One day…” delayed payoff", "You ___ over and over. Then one day, ___.",
     ["START", "BRIDGE", "RELATE"], None, "Her 3yo caption line: 'You repeat the same \"sss\"… Then one day…'."),
    ("relatable-admission", "Relatable admission", "Sometimes I ___ . Other times ___.",
     ["RELATE"], "Some days I ___. Other days ___.", "Voice: don't open on 'Sometimes'. The winging-it caption ends 'Some days I'm completely sure… Other days I question everything'."),
    ("what-happens-when", "“What happens when…”", "What happens when you ___?",
     ["TEACH", "PROVE"], None, ""),
    ("wanted-to-see", "“I wanted to see…”", "I wanted to see if ___ . Here’s what happened.",
     ["START", "PROVE"], "I wanted to see if ___. This is what happened.", "Voice: drop 'Here's what'. Day 7 overlay was this shape: '…Let's see if he can find it in a book…'."),
    ("x-is-one-thing", "“X is one thing…” contrast", "___ is one thing. But can ___?",
     ["BRIDGE", "PROVE"], None, "e.g. 'Knowing R is one thing. But can he find it in a book?'."),
    ("next-step", "“The next step…”", "You’ve ___ . What do you do next?",
     ["TEACH", "BRIDGE"], None, ""),
    ("problem-tiny-solution", "Specific problem → tiny solution", "If ___, try ___.",
     ["TEACH"], "___? Try ___.", "Voice: avoid the 'If…' conditional opener."),
    ("turns-out", "“Turns out…”", "Turns out, ___.",
     ["RELATE", "PROVE"], None, ""),
    ("confession-consequence", "Confession → consequence", "I ___ . Now ___.",
     ["RELATE", "SHARE"], None, ""),
    ("i-know-because", "“I know because…”", "I know because ___.",
     ["RELATE"], None, "Her own move in the 3yo caption: 'I know because not long ago, my 3yo was that toddler too.'"),
]
BY_ID = {h[0]: h for h in HOOKS}

EXTRA_FLAGS = [
    (r"^\s*sometimes\b", "opens on \"Sometimes\" (banned opener)"),
    (r"^\s*if (you|your)\b", "\"If you…\" conditional opener (voice rule; also underperformed)"),
]


def voice_issues(text):
    issues = []
    text = text.replace("’", "'").replace("‘", "'")  # her formats use curly apostrophes
    low = text.lower()
    for w in BANNED_WORDS:
        if re.search(rf"\b{re.escape(w)}\b", low):
            issues.append(f"banned word \"{w}\"")
    for pat, label in BANNED_PATTERNS + EXTRA_FLAGS:
        if re.search(pat, text, flags=re.I):
            issues.append(label)
    return issues


def blanks(template):
    return re.findall(r"___|\[[^\]]+\]", template)


def cmd_list(a):
    rows = [h for h in HOOKS if not a.pillar or a.pillar.upper() in h[3]]
    if a.pillar and a.pillar.upper() not in PILLARS:
        raise SystemExit(f"Unknown pillar {a.pillar}. Use one of: {', '.join(PILLARS)}")
    for hid, name, tpl, pillars, safe, _ in rows:
        flag = " ⚠ voice" if voice_issues(tpl) else ""
        print(f"{hid:24} {name}{flag}\n{'':24} {tpl}   [{', '.join(pillars)}]")
    print(f"\n{len(rows)} format(s). ⚠ = clashes with the voice file; `show ID` gives a voice-safe version.")


def cmd_show(a):
    if a.id not in BY_ID:
        raise SystemExit(f"Unknown id. Run `list` to see ids.")
    hid, name, tpl, pillars, safe, notes = BY_ID[a.id]
    print(f"{name}  ({hid})\nOriginal:   {tpl}")
    issues = voice_issues(tpl)
    if issues:
        print(f"Voice flags: {'; '.join(issues)}")
    if safe:
        print(f"Voice-safe: {safe}")
    print(f"Pillars:    {', '.join(pillars)}")
    if notes:
        print(f"Notes:      {notes}")


def cmd_fill(a):
    if a.id not in BY_ID:
        raise SystemExit("Unknown id. Run `list` to see ids.")
    hid, name, tpl, pillars, safe, notes = BY_ID[a.id]
    base = safe if (safe and not a.original) else tpl
    slots = blanks(base)
    if len(a.values) != len(slots):
        raise SystemExit(f"This format has {len(slots)} blank(s): {', '.join(slots)}. You gave {len(a.values)}.")
    out = base
    for v in a.values:
        out = re.sub(r"___|\[[^\]]+\]", lambda m: v, out, count=1)
    out = re.sub(r"\s+([.,?!:])", r"\1", out)
    print(out)
    issues = voice_issues(out)
    print("✓ voice check passed" if not issues else "✗ " + "; ".join(issues))


def cmd_lint(a):
    issues = voice_issues(a.text)
    print("✓ voice check passed" if not issues else "✗ " + "; ".join(issues))


def main():
    ap = argparse.ArgumentParser(description="The viral hook library for @threelittlereaders.")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("list"); p.add_argument("--pillar")
    p = sub.add_parser("show"); p.add_argument("id")
    p = sub.add_parser("fill"); p.add_argument("id"); p.add_argument("values", nargs="*")
    p.add_argument("--original", action="store_true", help="Fill her original wording even if a voice-safe version exists")
    p = sub.add_parser("lint"); p.add_argument("text")
    a = ap.parse_args()
    {"list": cmd_list, "show": cmd_show, "fill": cmd_fill, "lint": cmd_lint}[a.command](a)


if __name__ == "__main__":
    main()
