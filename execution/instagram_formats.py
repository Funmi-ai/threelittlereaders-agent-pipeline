#!/usr/bin/env python3
"""
Instagram Formats — the @threelittlereaders Format Finder. Given a post, it
decides what SHOULD be shown (the video format that best proves this post's
message to Sally) and hands back a film plan, instead of starting from
whatever footage happens to exist.
SOP: directives/threelittlereaders/format_finder.md

Modelled on OnePeak Creative's Format Finder (researched 26 Oct 2026): a
library of named, repeatable formats in three families (Challenge,
Storytelling, Educational), matched to the niche, then hook → script → shot
list. Ours swaps their generic "65+ formats" for formats rebuilt for a
parent-confidence early-reading account, and ranks them against this
account's own results rather than claims.

How `find` ranks (deterministic, every number shown in the output):
  the moment   +5 if the idea describes this format's kind of moment (a word
               chain, a refusal, a callback…): the strongest evidence of what
               the post is.
  message fit  what the post must make Sally believe (inferred from the idea,
               or --message). Primary ×3 (×1.5 when only the pillar's default),
               secondary ×1.5.
  goal fit     the pillar's job (follow / save / share / comment / watch) ×3.
  pillar       +1 if the format is built for this pillar.
  child        −3 if the format can't show the post's child (e.g. b-roll for a
               moment that belongs to the 3yo).
  our results  +1.5 / −1 when this format beat / trailed the account median on
               the goal's metric (n≥2; half that at n=1). Untested → 0, flagged.
               Rates built on fewer than 3 actions (2 follows, 1 send) don't count.
  recency      −1.5 if the same format was used in the last 5 days.

Subcommands:
  find    --id IG-0xx | --idea "…" [--pillar] [--child] [--message] [--goal]
          rank the formats for this post, ★ the best, print its film plan
  plan    FORMAT [--child middle]   the film plan for one format
  list    [--family Challenge]      every format, one line each
  stats                             how each format has done on this account
  log     --post IG-0xx --format ID [--shape ID]   record a post's format
          (--shape: the format a daily vlog was shaped as)

Usage:
    python3 execution/instagram_formats.py find --id IG-069
    python3 execution/instagram_formats.py find --idea "5yo reads to his brothers at bedtime" --pillar PROVE
    python3 execution/instagram_formats.py plan word-chain
    python3 execution/instagram_formats.py log --post IG-085 --format word-chain
    python3 execution/instagram_formats.py stats
"""

import argparse
import csv
import re
import sys
from datetime import date, timedelta
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parent.parent / "outputs" / "instagram" / "format_log.csv"
FIELDS = ["post", "format", "shape", "logged", "note"]

MESSAGES = {
    "possible": "a normal mum could get her child here (proof of possibility)",
    "method": "this is how to do it: something she can copy tonight",
    "permission": "what she's already doing is fine; small still matters",
    "relatable": "this mum isn't Perfect Teaching Mum either",
    "progress": "look how far it's come over time",
    "everywhere": "learning fits into ordinary life, no prep",
    "real": "the funny, unpolished moment: kids don't cooperate on cue",
    "conversation": "tell me yours: her turn to talk",
    "myth": "the thing she was told she must do first isn't a rule",
}
GOALS = {"follow": "follows/1k", "save": "saves", "share": "sends", "comment": "comments", "watch": "skip rate"}
RAW = {"follow_rate": "follows", "save_rate": "saves", "share_rate": "shares", "comment_rate": "comments"}
MIN_ACTIONS = 3
GOAL_METRIC = {"follow": ("follow_rate", True), "save": ("save_rate", True), "share": ("share_rate", True),
               "comment": ("comment_rate", True), "watch": ("skip_rate", False)}
# The pillar's job (directives/instagram_content.md pillar table)
PILLAR_GOAL = {"PROVE": "follow", "BRIDGE": "follow", "RELATE": "follow", "START": "watch",
               "SHARE": "share", "TEACH": "save", "COMMUNITY": "comment"}
PILLAR_MESSAGE = {"PROVE": "possible", "BRIDGE": "progress", "RELATE": "relatable", "START": "progress",
                  "SHARE": "real", "TEACH": "method", "COMMUNITY": "conversation"}
CHILDREN = {"youngest": "the youngest (Stage 1: sounds)", "middle": "the 3yo (Stage 2: building)",
            "eldest": "the 5yo (Stage 3: independence)", "none": "no child on screen (her, hands, b-roll)"}
CHILD_ALIASES = [(r"\b(1[0-9]|2[0-4])\s?mo\b|\byoungest\b|\btoddler\b|\b1yo\b|\b2yo\b", "youngest"),
                 (r"\b[34]\s?yo\b|\bmiddle\b|\b[34]\s?year", "middle"),
                 (r"\b[56]\s?yo\b|\beldest\b|\b[56]\s?year", "eldest"),
                 (r"\bmy third\b|\bthe baby\b", "youngest")]
# Keyword cues for the message a post is carrying. Legible on purpose: the output
# says which words matched, and --message overrides when the cues miss.
MESSAGE_CUES = {
    "possible": r"spell|unfamiliar|himself|no help|worked (it )?out|by himself|reads\b|reading (to|alone|without)|independ|never taught",
    "method": r"\bhow\b|method|technique|game called|\bsteps?\b|\bways\b|dots? and (a )?line|what to do|things to say|\bprompts?\b|accidental lesson",
    "permission": r"to the mum|still matters|trying her best|behind|scared|wrong|guilt|not seeing results|only managed|it's ok|that's ok",
    "relatable": r"confess|\bhide\b|winging|admit|i thought i|bribe|gym|embarrass|honest",
    "progress": r"journey|then\b.*\bnow|recap|day 1\b|at age|archiv|throwback|old video|couldn't|yesterday|callback|payoff|weeks? ago",
    "everywhere": r"park|cereal|road sign|number plate|everywhere|washing machine|label|out and about|laptop|keyboard|car\b|supermarket|bath",
    "real": r"said no|says no|no to every|blooper|outtake|backfired|funny|comedic|cancelled|refus|meltdown|letterbox",
    "conversation": r"comment|crowdsourc|\bvote\b|your (kid|child)'?s? (favourite|one)|tell me|ask (them|mums)",
    "myth": r"myth|don'?t need|letter names|had to|supposed to|before you can|too early|too late|curriculum|satpin|should know|right order",
}

# One entry per format. beats: (seconds, what's on screen, what the overlay does).
# film: the shot list to capture on the day. hooks: ids in instagram_hooks.py.
# Every plan inherits the face rule: side angles only, never front-facing.
FORMATS = {
    # ---- Challenge: the viewer watches a child solve something live -------------------------
    "word-chain": dict(
        name="Word chain: watch him solve it", family="Challenge",
        origin="their Quiz / challenge formats: a live test the viewer plays along with",
        shows="A child changing one letter at a time to make a new word, on his own, in real time.",
        messages={"possible": 3, "progress": 1, "method": 1}, goals={"follow": 3, "watch": 3, "share": 1},
        children=["middle", "eldest"], pillars=["BRIDGE", "PROVE"],
        beats=[(2, "Tiles laid out, first word already made, his hand in shot", "the challenge in ≤7 words"),
               (4, "You say the next word; his hand starts moving", "the target word, nothing else"),
               (6, "He swaps the tile(s), sounding it out under his breath", "silent: let the sounding-out carry it"),
               (5, "The bigger jump: a word with no shared letters", "raise the stakes: 'This one's harder'"),
               (3, "Finished word, hands off the table", "the payoff, plainly stated")],
        film=["Overhead or side angle on the tiles (no face)", "Keep the audio: his sounding-out is the hook",
              "Plan 3–4 words that get harder, ending on one that shares no letters",
              "Don't cut the hesitation; a 2s pause holds better than a clean answer"],
        hooks=["what-can-open-loop", "proof", "wasnt-even", "before-after"],
        watch_out="Possibility, not superiority: frame the game, not his level. Never 'my 3yo can already…'.",
        evidence="IG-047 grape→sham: 2,050 reach, 6.3 follows/1k (best follow rate on a reel). IG-063 SOP→STOP: 2,074 reach.",
        cues=r"->|→|word chain|word swap|\bswaps?\b|letter[- ]tiles?"),
    "unfamiliar-word": dict(
        name="Unfamiliar word: can he spell it?", family="Challenge",
        origin="their 'Can you tell the difference?' tension: will he get it?",
        shows="The eldest spelling a long word he's never been taught, including the wobble and the self-correction.",
        messages={"possible": 3, "myth": 1}, goals={"follow": 3, "watch": 2, "comment": 1},
        children=["eldest"], pillars=["PROVE"],
        beats=[(2, "Whiteboard, marker in his hand, the word said aloud", "the word and 'never taught'"),
               (8, "He writes, sounding out in chunks", "name the rule he's using, in plain words"),
               (4, "The wobble: a wrong letter, a pause", "silent, or 'Watch this bit'"),
               (4, "He fixes it himself", "what he did when he didn't know"),
               (2, "Finished word", "the Granular line: what to do when you don't know")],
        film=["Side angle on the whiteboard, his hand and the marker", "Pick a word that tests a rule he knows",
              "Keep the mistake in: the self-correction is the point"],
        hooks=["proof", "im-not-but", "i-know-because"],
        watch_out="The impressive word is the risk. Lead with what he does when he doesn't know, never the word's difficulty.",
        evidence="IG-001 Granular: 1,203 reach. IG-011: 1,328 reach. IG-058 Articulating: 1,299 reach, 1.5 follows/1k. Articulate was the account's best follower post.",
        cues=r"spells? '|unfamiliar word|spell(s|ing)? an unfamiliar|never taught (him )?(that|the) word"),
    "play-along": dict(
        name="Pause and play along", family="Challenge",
        origin="their Quiz format, turned on the viewer: Sally (and her child) guess first",
        shows="Letters on the table, a beat for the viewer to read it, then the child reads it.",
        messages={"method": 2, "possible": 2, "conversation": 1}, goals={"watch": 3, "comment": 2, "share": 2},
        children=["middle", "eldest"], pillars=["BRIDGE", "TEACH"],
        beats=[(2, "The tiles, full frame", "'Can your little one read this before mine?'"),
               (2, "Hold on the tiles, no hands", "a countdown or 'Pause here'"),
               (4, "He sounds it out", "silent"),
               (3, "Next word, harder", "'Level 2'"),
               (3, "The answer", "invite: 'Play it with yours tonight'")],
        film=["Static overhead shot of the tiles (easy to hold for the pause)",
              "3 words that rise in difficulty", "A clean shot of each word before he touches it"],
        hooks=["pov", "what-can-open-loop", "think-you-need"],
        watch_out="Untested on this account. Not a test of Sally's child: 'play it with yours', never 'can yours do this?'.",
        evidence="New to the account.",
        cues=r"play along|\bguess\b|pause (here|and)"),
    "mystery-bag": dict(
        name="Mystery letter bag", family="Challenge",
        origin="their Blindfold Test: a reveal the viewer waits for",
        shows="He pulls a letter out of a bag or box without looking, and says (or finds) the sound.",
        messages={"progress": 2, "possible": 1, "real": 1, "everywhere": 1}, goals={"watch": 3, "share": 1},
        children=["youngest", "middle"], pillars=["START", "BRIDGE"], vlog_ok=True,
        beats=[(2, "Hand going into a bag or a household tub", "'What will he pull out?'"),
               (3, "The letter comes out", "silent: let the viewer guess the sound"),
               (3, "He says the sound (or doesn't)", "the sound, or the honest outcome"),
               (4, "Two or three more pulls, quicker", "the running tally"),
               (2, "The one he loved", "a warm one-line landing")],
        film=["Any bag, sock or tub: no special kit", "Side angle on his hands and the bag",
              "Load it with sounds he knows plus one new one"],
        hooks=["what-happens-when", "pov", "one-day"],
        watch_out="Untested. Fine if he gets it wrong: show the real outcome, never re-shoot for a clean run.",
        evidence="New to the account.",
        cues=r"\bbag\b|mystery|feels? the letter"),
    "he-quizzes-me": dict(
        name="He quizzes me", family="Challenge",
        origin="their Quiz With Consequences, reversed: the child is the teacher",
        shows="The 5yo (or 3yo) tests her on spellings or sounds; the loser reads the bedtime story.",
        messages={"real": 2, "relatable": 2, "possible": 1}, goals={"share": 3, "comment": 2, "watch": 2},
        children=["eldest", "middle"], pillars=["SHARE", "RELATE"],
        beats=[(2, "Him holding the marker, her at the board", "the stakes: 'Loser reads the bedtime story'"),
               (5, "He gives her a word; she tries", "his word, in his voice"),
               (4, "He corrects her (gently or not)", "the role reversal, plainly"),
               (4, "Her turn to quiz him", "the score"),
               (3, "Who reads tonight", "the warm, funny landing")],
        film=["Side angle with both of you in, faces turned away", "Let him pick the words",
              "Keep the banter audio; it carries the reel"],
        hooks=["can-no-longer", "nobody-warned-me", "unexpected-consequences"],
        watch_out="Untested. Keep it playful; his corrections should land as funny, never smug.",
        evidence="New to the account. Closest idea: IG-012 (spelling backfired, banked).",
        cues=r"quiz(zes|zed)? me|tests? me|role reversal"),
    "which-book-wins": dict(
        name="Which book wins?", family="Challenge",
        origin="their Would You Rather: two options, the audience votes",
        shows="Two books side by side; he picks one; mums say which their child would pick.",
        messages={"conversation": 3, "everywhere": 1}, goals={"comment": 3, "save": 1},
        children=["youngest", "middle", "eldest", "none"], pillars=["COMMUNITY"],
        beats=[(2, "Two book covers side by side", "'Which one would yours pick?'"),
               (3, "His hand hovers", "silent"),
               (3, "He picks", "his pick"),
               (2, "The book open on his lap", "the comment ask: age + one book")],
        film=["Overhead of two covers on the floor", "His hand reaching (no face)", "One clip of him with the pick"],
        hooks=["dear-algorithm", "recommendation-list"],
        watch_out="Untested. The comment ask goes in the overlay, never as a question in the caption (caption rule).",
        evidence="New to the account. Closest idea: IG-016 (crowdsourced bookshelf, banked).",
        cues=r"which book|\bvote\b|book (pick|choice)"),

    # ---- Storytelling: a moment with a beginning, middle and end ----------------------------
    "daily-vlog": dict(
        name="Day N vlog", family="Storytelling",
        origin="their Personal Story format as a series: the same opener every day, a new moment each time",
        shows="The youngest's session today, opened with the fixed 'Day N teaching my 20mo to read' line.",
        messages={"progress": 3, "real": 1}, goals={"watch": 3},
        children=["youngest"], pillars=["START"],
        beats=[(2, "Today's first moment", "the fixed opener: 'Day N teaching my 20mo to read'"),
               (8, "The session, shaped by the format it's shaped as (see find)", "one card (single-card rule)")],
        film=["Whatever the session was. `find` suggests the shape to film it as."],
        hooks=["one-day", "it-started-with"],
        watch_out="The opener stays fixed (standing rule). Single card for the youngest, never the multi-beat template.",
        evidence="Day-N vlogs: 200–1,550 reach. Best skip: IG-079 washing machine 20%, IG-023 laptop 24%.",
        cues=r"(?!)"),
    "confession-broll": dict(
        name="Confession over b-roll", family="Storytelling",
        origin="their Personal Story format: a one-line admission over ordinary footage of her life",
        shows="Her (or her hands, or her life) in an ordinary moment, under one honest line; the caption tells the story.",
        messages={"relatable": 3, "permission": 2, "myth": 1}, goals={"follow": 2, "share": 2, "watch": 2},
        children=["none"], pillars=["RELATE"],
        beats=[(3, "Ordinary b-roll: gym, school run, kitchen", "the confession, one line"),
               (4, "Keep the b-roll moving", "the turn: what it means for teaching"),
               (3, "A calmer shot", "the landing line")],
        film=["5–10s of a real, ordinary moment, not posed", "No reading content needed",
              "Steady phone, natural light"],
        hooks=["no-longer-embarrassed", "relatable-admission", "i-thought-i-needed", "contradiction"],
        watch_out="Draws profile visits more than follows (IG-003: 24+ visits, 2 follows). Bridge back to reading by the caption's end.",
        evidence="IG-003 winging it: 1,545 reach, 17% skip (best on the account). IG-068 gym: 1,164 reach, 21% skip. IG-046: 544 reach.",
        cues=r"b-?roll|\bgym\b|confess|\bhide\b"),
    "to-the-mum": dict(
        name="To the mum who…", family="Storytelling",
        origin="their Personal Story format, aimed at the viewer: direct-address reassurance",
        shows="Calm footage of the kids learning, under a line spoken straight to the mum who's worried.",
        messages={"permission": 3, "relatable": 1}, goals={"follow": 3, "share": 2, "save": 1},
        children=["youngest", "middle", "eldest", "none"], pillars=["PROVE"],
        beats=[(3, "A quiet, warm shot (a lantern, a book, small hands)", "'To the mum who…' + reassurance, one line"),
               (5, "The child doing something small", "how to read the video: 'This is what … looks like'"),
               (4, "A wider, softer shot", "the landing")],
        film=["Golden-hour or lamp-lit footage", "Any small learning moment", "One wide establishing shot"],
        hooks=["direct-reassurance", "you-dont-need"],
        watch_out="Never two 'To the mum…' openers on the same day. The caption follows the formula (it was built from this format).",
        evidence="IG-008 5 minutes: 1,507 reach, 3.3 follows/1k (the formula's source). IG-006: 3.9 follows/1k.",
        cues=r"to the mum"),
    "then-vs-now": dict(
        name="Then vs now", family="Storytelling",
        origin="their First vs Pro: the same child, two points in time",
        shows="An old clip of a child at an earlier stage, cut against the same child now doing the next thing.",
        messages={"progress": 3, "possible": 2}, goals={"follow": 3, "share": 1, "save": 1},
        children=["youngest", "middle", "eldest"], pillars=["PROVE", "BRIDGE"], vlog_ok=True,
        beats=[(3, "THEN: the old clip, labelled with age", "'At 2:' / 'Day 1:'"),
               (3, "Hard cut to NOW: the same activity, further on", "'Now:'"),
               (4, "What happened in between, in one honest line", "the small daily thing that bridged it"),
               (2, "Now, wider", "the landing")],
        film=["Find the oldest usable clip (check faces)", "Film NOW doing the same activity, from the same angle",
              "Match framing so the cut lands"],
        hooks=["and-to-think", "before-after", "it-started-with"],
        watch_out="The gap between clips must be honest (dates from the kids profile). Possibility, not 'look how advanced'.",
        evidence="Untested as a straight cut. Closest: IG-072 archival 2½yo (1,340 reach, 24% skip).",
        cues=r"then vs now|first vs|back then|now vs"),
    "progress-montage": dict(
        name="Every sound in N days", family="Storytelling",
        origin="their recap/compilation formats: lots of small wins in one quick run",
        shows="Quick cuts of each sound or word he's learned over a stretch, each with its date.",
        messages={"progress": 3, "possible": 1}, goals={"follow": 2, "watch": 2},
        children=["youngest", "middle", "eldest"], pillars=["BRIDGE", "START"], vlog_ok=True,
        beats=[(2, "The first win", "the stretch: 'One week. Five sounds.'"),
               (8, "1–1.5s per clip, one sound each", "the sound + day, as a running list"),
               (3, "Today's clip, held longer", "what today added")],
        film=["Pull every clip from the period", "One fresh clip today to end on", "Keep each clip to its peak second"],
        hooks=["timeframe-input-result", "what-can-open-loop"],
        watch_out="IG-019 (week-one recap) skipped at 52%: open on the strongest clip, not the first chronologically.",
        evidence="IG-019 recap: 201 reach, 52% skip (weak opening clip).",
        cues=r"recap|every sound|week (one|two|1|2)|journey montage"),
    "plan-vs-reality": dict(
        name="What I planned vs what he did", family="Storytelling",
        origin="their Personal Story twist: expectation, then the real thing",
        shows="The lesson she set up, then the child doing something else, and her following his lead into it.",
        messages={"real": 3, "relatable": 2, "everywhere": 1, "permission": 1}, goals={"share": 3, "watch": 2},
        children=["youngest", "middle"], pillars=["START", "SHARE", "RELATE"], vlog_ok=True,
        beats=[(2, "The plan: letters set out neatly", "'The plan:'"),
               (3, "What he did instead", "'What he did:'"),
               (5, "Her following his lead, still saying the sounds", "the lesson still happened"),
               (2, "Him happy in it", "the landing")],
        film=["One shot of the set-up before he arrives", "Keep filming when it goes off-plan; that's the reel",
              "Side angle, his hands and the object"],
        hooks=["expectation-reality", "pov", "turns-out"],
        watch_out="If he refuses outright, with no turn, it reads as a flop (IG-080, 64% skip). Film it only if there's a turn.",
        evidence="IG-021 Nutribullet letterbox: 326 reach, 36% skip. IG-080 'says no to every letter': 279 reach, 64% skip (no turn).",
        cues=r"about to (start|do)|planned|lesson plan|turned the \w+ into"),
    "struggle-to-win": dict(
        name="Couldn't, then could", family="Storytelling",
        origin="their Personal Story arc: a setback, then the payoff",
        shows="A clip of him not getting something, then a later clip of him getting it, with the gap named.",
        messages={"progress": 2, "permission": 2, "possible": 1}, goals={"follow": 2, "watch": 2, "comment": 1},
        children=["youngest", "middle", "eldest"], pillars=["START", "BRIDGE"], vlog_ok=True,
        beats=[(3, "The miss: he can't find or say it", "'Day 7: he couldn't find R'"),
               (2, "Beat of nothing", "'Six days later?'"),
               (4, "He gets it, unprompted", "silent: the payoff speaks"),
               (2, "Her reaction or his", "the permission line")],
        film=["Needs both clips: the miss and the win", "Same object or book in both, so the payoff reads instantly"],
        hooks=["one-day", "before-after", "wasnt-even"],
        watch_out="Only with a real miss on film. The reluctant-child angle (IG-073) didn't fit the account's tone.",
        evidence="IG-032 R in the book: 1,064 reach, 38% skip, 0.9 follows/1k. IG-073 reluctant child: 231 reach, deleted.",
        cues=r"couldn'?t|callback|payoff|before/after|days? later|finally"),
    "single-clip-proof": dict(
        name="Just watch", family="Storytelling",
        origin="their simplest format: one uncut clip, one line, nothing else",
        shows="One continuous clip of a child doing the thing (reading alone, finding a letter), under a single card.",
        messages={"possible": 3}, goals={"follow": 2, "watch": 1},
        children=["youngest", "middle", "eldest"], pillars=["PROVE", "START"], vlog_ok=True,
        beats=[(8, "One uncut clip, audio on", "one card, ending in an ellipsis or a plain statement")],
        film=["8–12s, one take, side angle", "Choose the take where something happens in the first 2s"],
        hooks=["proof", "wasnt-even", "i-know-because"],
        watch_out="Only works if the first 2 seconds already show the thing. No build-up.",
        evidence="IG-084 (5yo reading to himself, 26 Oct): numbers not synced yet.",
        cues=r"single clip|one \d+[–-]?\d*s clip|teaser|reads? (to himself|a book)"),

    # ---- Educational: she walks away able to do something ---------------------------------------
    "how-i-do-it": dict(
        name="The game, shown once", family="Educational",
        origin="their Did You Know / tutorial formats: one technique, demonstrated",
        shows="One named game or technique, shown in one clean run with the child, so Sally can copy it tonight.",
        messages={"method": 3, "myth": 1}, goals={"save": 3, "share": 2, "follow": 1},
        children=["youngest", "middle", "eldest", "none"], pillars=["TEACH"],
        beats=[(2, "The kit (blocks, whiteboard) and the game's name", "'Swap the Sound: the game that…'"),
               (6, "One full round with him", "each step, ≤7 words"),
               (4, "A second, faster round", "the rule in one line"),
               (2, "The kit, tidied", "'All you need: …'")],
        film=["Overhead on hands and kit", "One clean round, then one quick one",
              "A 2s shot of just the kit for the end card"],
        hooks=["problem-tiny-solution", "you-dont-need", "experience-authority"],
        watch_out="Name the game; keep it to one technique. 'A few steps ahead', never expert.",
        evidence="IG-078 Swap the Sound: 1,280 reach, 25% skip.",
        cues=r"game,? called|it'?s called|technique|\bprompts?\b|things to say|how (to|i)\b"),
    "throwback-method": dict(
        name="Found this old video", family="Educational",
        origin="their Personal Story + Did You Know hybrid: an old clip that teaches",
        shows="Archival footage of an older child at 2 being taught one technique, with the method named.",
        messages={"method": 2, "progress": 2, "possible": 1}, goals={"save": 2, "follow": 2, "watch": 1},
        children=["middle", "eldest"], pillars=["TEACH", "BRIDGE"],
        beats=[(3, "The old clip, age labelled", "'I found this old video of my eldest at 2½…'"),
               (6, "The technique in action", "name the steps"),
               (3, "A shot of him now (optional)", "where it led")],
        film=["Search the camera roll for the earliest teaching clips", "Check faces (side angles only)",
              "Optional: 3s of him now for the close"],
        hooks=["it-started-with", "and-to-think", "one-day"],
        watch_out="Archive is finite. Save it for methods Sally can copy, not just nostalgia.",
        evidence="IG-072 two dots and a line: 1,340 reach, 24% skip.",
        cues=r"archiv|old (video|clip|footage)|at age 2|when he was (just )?2"),
    "everyday-spot": dict(
        name="Phonics hiding in…", family="Educational",
        origin="their Did You Know format, set in ordinary life",
        shows="A sound found in an everyday object (a washing machine, a number plate, a cereal box), with the child joining in.",
        messages={"everywhere": 3, "method": 2, "permission": 1}, goals={"save": 2, "share": 2, "watch": 1},
        children=["youngest", "middle", "eldest", "none"], pillars=["TEACH", "START"], vlog_ok=True,
        beats=[(2, "The object, full frame", "'Today's phonics activity was… [object]'"),
               (5, "Her saying the sound; him copying", "the sound"),
               (3, "A second object, quickly", "'It's everywhere once you look'"),
               (2, "Him carrying on playing", "the landing")],
        film=["Whatever he's obsessed with today", "Close-ups of letters on real things (no faces needed)",
              "His hands on the object"],
        hooks=["pov", "problem-tiny-solution", "x-is-one-thing"],
        watch_out="The object is the hook. Pick what he's obsessed with, not what's tidy.",
        evidence="IG-079 washing machine: 1,257 reach, 20% skip. IG-023 laptop: 1,552 reach, 24% skip. IG-027 keyboard: 1,166 reach.",
        cues=r"washing machine|cereal|number plate|road sign|\bpark\b|laptop|keyboard|\blabel|everywhere|supermarket"),
    "myth-check": dict(
        name="You were told… we didn't", family="Educational",
        origin="their Did You Know myth-bust, made gentle",
        shows="One 'rule' Sally worries about (letter names first, SATPIN order, too early), then footage of what they did instead.",
        messages={"myth": 3, "method": 1, "permission": 1}, goals={"save": 2, "share": 2, "comment": 2},
        children=["youngest", "middle", "eldest"], pillars=["TEACH"],
        beats=[(3, "Child mid-activity", "the worry, in her words: 'I thought I had to teach letter names first'"),
               (5, "What they did instead", "the alternative, plainly"),
               (3, "The result", "'It's one way, not the only way'")],
        film=["The activity that contradicts the rule", "A clip that shows it working"],
        hooks=["i-thought-i-needed", "think-you-need", "you-dont-need", "contradiction"],
        watch_out="Never knock schools, SATPIN or programmes. 'This worked for us', never 'they're wrong'.",
        evidence="New as a reel. Supported by the kids profile (no letter names, capitals first, sounds out of order).",
        cues=r"letter names|satpin|curriculum|reading level|too early|should be reading"),
    "carousel-breakdown": dict(
        name="Numbered breakdown (carousel)", family="Educational",
        origin="their list/breakdown formats, as slides: no footage needed",
        shows="Her real method as 5–8 numbered slides, each one a thing she did, in her words.",
        messages={"method": 3, "relatable": 1, "myth": 1}, goals={"save": 3, "follow": 2},
        children=["none"], pillars=["TEACH"],
        beats=[(0, "Slide 1: cover (real photo, small lowercase text)", "the claim"),
               (0, "Slides 2–7: one point each", "≤30 words a slide"),
               (0, "Last slide: the landing", "the line she'd put on a lockscreen")],
        film=["One real photo for the cover (IG cover style)", "No video needed: Carousel Builder takes it from here"],
        hooks=["recommendation-list", "things-i-dont-do", "i-thought-i-needed"],
        watch_out="Small reach, strong follows: use it when the post's job is follows from people already looking.",
        evidence="IG-060 love for reading: 231 reach but 8.7 follows/1k (highest rate on the account).",
        cues=r"carousel|\bslides\b|\d-point|breakdown"),
    "consequence-skit": dict(
        name="Nobody warned me: the side effect", family="Storytelling",
        origin="their skit / Personal Story formats: an everyday scene with an unexpected twist",
        shows="An ordinary family moment where teaching him to read comes back to bite (spelling a secret to her husband, and the 5yo answers).",
        messages={"real": 3, "relatable": 2, "possible": 1}, goals={"share": 3, "watch": 2, "comment": 1},
        children=["eldest", "middle"], pillars=["SHARE"],
        beats=[(2, "The set-up: her spelling a word out to her husband", "the side effect, as a 'Nobody warned me…' line"),
               (3, "The child answering from across the room", "silent: his answer is the punchline"),
               (2, "Her reaction (back of head, or hands)", "the turn"),
               (2, "Him carrying on, unbothered", "the landing")],
        film=["Re-create a real moment it happened (say so in the caption if staged)",
              "His voice from off-camera works, no face needed", "Keep it short: the punchline lands by 5s"],
        hooks=["nobody-warned-me", "unexpected-consequences", "downside-of", "can-no-longer"],
        watch_out="Untested. Only re-create things that really happen; never invent what he can do.",
        evidence="New to the account. Banked idea: IG-012 (spelling backfired).",
        cues=r"backfired|nobody warned|anymore|unexpected|consequence|spell(ing)? (things )?to my"),
    "blooper-montage": dict(
        name="Every 'no' from one session", family="Storytelling",
        origin="their compilation/humour formats: one session's outtakes, cut fast",
        shows="Rapid cuts of every refusal, wriggle and 'I don't want to' from one session, ending on the one moment it worked.",
        messages={"real": 3, "relatable": 2}, goals={"share": 3, "watch": 1},
        children=["youngest", "middle", "eldest"], pillars=["SHARE"],
        beats=[(1, "The first 'no'", "the set-up: 'How it looks on Instagram vs…'"),
               (6, "Fast cuts: 0.5–1s each", "a running count of no's"),
               (3, "The one moment it worked", "the turn"),
               (2, "Hold on it", "the landing")],
        film=["Keep the camera running through the bad bits", "Needs one real success to end on"],
        hooks=["expectation-reality", "weird-silly", "downside-of"],
        watch_out="Must end on a turn, or it's the IG-080 problem. Funny, never exasperated at the child.",
        evidence="IG-075 (cut from the IG-073 session): hooked, not posted yet.",
        cues=r"every 'no'|refusals?|comedic montage|outtakes?|bloopers?"),
}


# --------------------------------------------------------------------------
# The log (which format each post used) and its results
# --------------------------------------------------------------------------
def read_log():
    if not LOG_FILE.exists():
        return []
    with LOG_FILE.open(newline="") as f:
        return list(csv.DictReader(f))


def write_log(rows):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def tracker():
    """(posts by id with metrics, plan records by id). Imported lazily so `plan`/`list` work without the xlsx."""
    from openpyxl import load_workbook
    from instagram_tracker import DEFAULT_OUTPUT
    from instagram_write import load_posts, plan_rows
    wb = load_workbook(DEFAULT_OUTPUT, data_only=True)
    posts = {str(p["id"]).upper(): p for p in load_posts(wb)}
    plan = {str(rec["id"]).upper(): rec for _, rec in plan_rows(wb["Content Plan"]) if rec["id"]}
    return posts, plan


def median(vals):
    vals = sorted(vals)
    if not vals:
        return None
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2


def format_results(posts, log):
    """{format: [post dicts]}, counting a vlog under both daily-vlog and its shape."""
    out = {}
    for row in log:
        p = posts.get(row["post"].upper())
        if not p or not p.get("reach"):
            continue
        for fid in {row["format"], row.get("shape") or ""} - {""}:
            out.setdefault(fid, []).append(p)
    return out


def evidence_score(fid, goal, results, posts):
    """(+1.5 / −1 / 0, reason) from this format's average on the goal's metric vs the account median."""
    key, higher_better = GOAL_METRIC[goal]
    baseline = median([p[key] for p in posts.values() if p.get(key) is not None and p.get("reach")])
    mine = [p[key] for p in results.get(fid, []) if p.get(key) is not None]
    if not mine or baseline is None:
        return 0, "untested here on this goal"
    if key in RAW:
        actions = sum(p.get(RAW[key]) or 0 for p in results.get(fid, []) if p.get(key) is not None)
        if actions < MIN_ACTIONS:
            return 0, f"only {actions:g} {RAW[key]} across {len(mine)} post(s): too few to read"
    avg = sum(mine) / len(mine)
    better = avg < baseline if not higher_better else avg > baseline
    same = abs(avg - baseline) < 1e-9
    fmt = (lambda v: f"{v:.0%}") if key == "skip_rate" else (lambda v: f"{v:.1f}/1k" if key == "follow_rate" else f"{v:.1%}")
    detail = f"{fmt(avg)} vs account {fmt(baseline)} ({GOALS[goal]}, n={len(mine)})"
    if same:
        return 0, detail + ": level"
    weight = 1 if len(mine) >= 2 else 0.5
    return (1.5 * weight, detail + ": better") if better else (-1 * weight, detail + ": worse")


# --------------------------------------------------------------------------
# Reading the post
# --------------------------------------------------------------------------
def infer_child(text):
    for pattern, child in CHILD_ALIASES:
        if re.search(pattern, text, re.IGNORECASE):
            return child
    return None


def infer_messages(text, pillar):
    """[(message, matched words)] strongest first; the pillar's default if nothing matches."""
    hits = []
    for msg, pattern in MESSAGE_CUES.items():
        found = sorted({m.group(0).lower() for m in re.finditer(pattern, text, re.IGNORECASE)})
        if found:
            hits.append((msg, found))
    # most cues first; on a tie, the message the pillar exists to carry
    hits.sort(key=lambda h: (-len(h[1]), h[0] != PILLAR_MESSAGE.get(pillar)))
    if not hits and pillar in PILLAR_MESSAGE:
        hits = [(PILLAR_MESSAGE[pillar], [f"{pillar} default"])]
    return hits


def recent_uses(log, plan, fid, around, days=5):
    out = []
    for row in log:
        if fid not in (row["format"], row.get("shape")):
            continue
        rec = plan.get(row["post"].upper(), {})
        when = rec.get("posted_date") or rec.get("date")
        if when and around and abs((when - around).days) <= days:
            out.append(f"{row['post']} {when:%-d %b}")
    return out


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def plan_lines(fid, child=None):
    f = FORMATS[fid]
    who = child if child in f["children"] else f["children"][0]
    total = sum(s for s, _, _ in f["beats"])
    out = [f"FILM PLAN · {f['name']} ({fid}) · {f['family']}",
           f"What to show: {f['shows']}",
           f"Who: {CHILDREN[who]}" + (f"  (built for: {', '.join(f['children'])})" if child and child not in f["children"] else ""),
           "Face rule: side angles only, never front-facing.", ""]
    if total:
        out.append(f"Beats (~{total}s):")
    else:
        out.append("Slides:")
    t = 0
    for secs, shot, overlay in f["beats"]:
        stamp = f"{t:>2}–{t + secs:<2}s" if secs else "  ·   "
        out.append(f"  {stamp}  {shot}\n           overlay: {overlay}")
        t += secs
    out += ["", "Capture on the day:"] + [f"  □ {x}" for x in f["film"]]
    out += ["", f"Pairs with hooks: {', '.join(f['hooks'])}  (instagram_hooks.py show ID)",
            f"Watch out: {f['watch_out']}",
            f"Evidence: {f['evidence']}"]
    return out


def cmd_find(a):
    posts, plan = tracker()
    log = read_log()
    rec = plan.get(a.id.upper()) if a.id else None
    if a.id and not rec:
        sys.exit(f"{a.id} isn't in the Content Plan.")
    idea = a.idea or (rec or {}).get("idea") or ""
    if not idea:
        sys.exit("Give --id or --idea.")
    text = " ".join(str(x) for x in (idea, (rec or {}).get("hook"), (rec or {}).get("caption")) if x)
    pillar = (a.pillar or (rec or {}).get("pillar") or "").upper() or None
    from instagram_write import is_fast_lane
    fast = bool(rec and is_fast_lane(rec))

    child = a.child or infer_child(text) or ("youngest" if fast else None)
    msgs = [(a.message, ["--message"])] if a.message else infer_messages(text, pillar)
    # A message read only from the pillar is a guess, so it weighs half and the moment leads.
    msg_weight = 1.5 if msgs and "default" in msgs[0][1][0] else 3
    primary = msgs[0][0] if msgs else None
    secondary = msgs[1][0] if len(msgs) > 1 else None
    goal = a.goal or PILLAR_GOAL.get(pillar, "follow")
    around = (rec or {}).get("date") or date.today()
    results = format_results(posts, log)

    ranked = []
    for fid, f in FORMATS.items():
        if fast and not f.get("vlog_ok"):
            continue
        if fid == "daily-vlog":
            continue  # fixed for the fast lane, never a choice; vlogs are ranked on their shape instead
        parts = []
        s = 0
        cue = sorted({m.group(0).lower() for m in re.finditer(f["cues"], text, re.IGNORECASE)})
        if cue:
            s += 5
            parts.append(f"moment ({', '.join(cue[:3])}) +5")
        m1 = msg_weight * f["messages"].get(primary, 0)
        s += m1
        parts.append(f"message {primary} +{m1:g}")
        if secondary and f["messages"].get(secondary):
            s2 = 1.5 * f["messages"][secondary]
            s += s2
            parts.append(f"{secondary} +{s2:g}")
        g = 3 * f["goals"].get(goal, 0)
        s += g
        parts.append(f"goal {goal} +{g:g}")
        if pillar and pillar in f["pillars"]:
            s += 1
            parts.append("pillar +1")
        if child and child not in f["children"]:
            s -= 3
            parts.append(f"can't show the {child} (needs {'/'.join(f['children'])}) −3")
        ev, ev_note = evidence_score(fid, goal, results, posts)
        s += ev
        parts.append(f"ours {ev:+g} ({ev_note})")
        used = recent_uses(log, plan, fid, around) if fid != "daily-vlog" else []
        used = [u for u in used if not (rec and u.startswith(rec["id"]))]
        if used:
            s -= 1.5
            parts.append(f"used {', '.join(used)} −1.5")
        ranked.append((s, fid, parts))
    ranked.sort(key=lambda r: -r[0])

    head = f"FORMAT FINDER · {rec['id'] if rec else 'new idea'}" + (" · FAST LANE: Day N vlog, ranked by shape" if fast else "")
    out = [head, f"  Idea: {idea[:160]}",
           f"  Message: {primary} ({MESSAGES.get(primary, '?')})  ← {', '.join(msgs[0][1]) if msgs else 'no cues'}"
           + (f"\n  Also: {secondary} ← {', '.join(msgs[1][1])}" if secondary else ""),
           f"  Goal: {goal} (judged on {GOALS[goal]})" + (f" · pillar {pillar}" if pillar else "")
           + f" · child: {CHILDREN[child] if child else 'not named (format decides)'}", ""]
    if not a.message and msgs and msgs[0][1] and "default" in msgs[0][1][0]:
        out.insert(3, "  (no message cues in the idea: pillar default used. Pass --message if that's wrong.)")
    for i, (s, fid, parts) in enumerate(ranked[:a.top]):
        star = "★" if i == 0 else " "
        out.append(f"{star} {s:>5.1f}  {fid:<20} {FORMATS[fid]['name']}")
        out.append(f"          {' · '.join(parts)}")
    out.append("")
    best = ranked[0][1]
    if "untested" in " ".join(ranked[0][2]):
        out.append("⚠ ★ is untested on this account on this goal: Researcher does web research first (roles/researcher.md).")
    out += plan_lines(best, child)
    if fast:
        out.append("\nThis is a daily vlog: keep the fixed 'Day N teaching my 20mo to read' opener and the single card.")
    out.append(f"\nOnce picked: python3 execution/instagram_formats.py log --post {rec['id'] if rec else 'IG-0xx'} "
               + (f"--format daily-vlog --shape {best}" if fast else f"--format {best}"))
    return out


def cmd_plan(a):
    if a.format not in FORMATS:
        sys.exit(f"Unknown format {a.format!r}. `list` shows them all.")
    return plan_lines(a.format, a.child)


def cmd_list(a):
    out = []
    for fam in ("Challenge", "Storytelling", "Educational"):
        rows = [(fid, f) for fid, f in FORMATS.items() if f["family"] == fam and (not a.family or a.family == fam)]
        if not rows:
            continue
        out.append(f"{fam}")
        for fid, f in rows:
            tested = "" if f["evidence"].startswith("IG-") or "reach" in f["evidence"] else "  (new)"
            out.append(f"  {fid:<20} {f['name']} [{', '.join(f['pillars'])}] · {', '.join(f['children'])}{tested}")
    out.append(f"\n{len(FORMATS)} formats. `plan ID` for the film plan, `find --id IG-0xx` to pick one for a post.")
    return out


def cmd_stats(a):
    posts, _ = tracker()
    log = read_log()
    results = format_results(posts, log)
    avg = lambda xs: sum(xs) / len(xs) if xs else None
    med = {k: median([p[k] for p in posts.values() if p.get(k) is not None and p.get("reach")])
           for k in ("reach", "skip_rate", "follow_rate")}
    out = [f"FORMATS ON THIS ACCOUNT · {len(log)} post(s) logged · account medians: reach {med['reach'] or 0:,.0f}"
           f" · skip {med['skip_rate'] or 0:.0%} · follows {med['follow_rate'] or 0:.1f}/1k",
           "Formats under 3 posts are an early signal, not a rule.", ""]
    rows = []
    for fid, ps in results.items():
        r, sk = avg([p["reach"] for p in ps]), avg([p["skip_rate"] for p in ps if p.get("skip_rate")])
        fo = avg([p["follow_rate"] for p in ps if p.get("follow_rate") is not None])
        rows.append((r or 0, fid, len(ps), r, sk, fo))
    for _, fid, n, r, sk, fo in sorted(rows, reverse=True):
        flag = "" if n >= 3 else "  (n<3)"
        out.append(f"  {fid:<20} {n} post(s) · reach {r:,.0f} · skip {f'{sk:.0%}' if sk is not None else '–'}"
                   f" · follows {f'{fo:.1f}/1k' if fo is not None else '–'}{flag}")
    untried = [fid for fid in FORMATS if fid not in results]
    if untried:
        out.append(f"\nNot tried yet: {', '.join(untried)}")
    unlogged = [pid for pid, p in posts.items() if p.get("reach") and pid not in {r['post'].upper() for r in log}]
    if unlogged:
        out.append(f"Posted but no format logged: {', '.join(sorted(unlogged))}")
    return out


def cmd_log(a):
    if a.format not in FORMATS or (a.shape and a.shape not in FORMATS):
        sys.exit("Unknown format. `list` shows them all.")
    rows = [r for r in read_log() if r["post"].upper() != a.post.upper()]
    rows.append({"post": a.post.upper(), "format": a.format, "shape": a.shape or "",
                 "logged": date.today().isoformat(), "note": a.note or ""})
    rows.sort(key=lambda r: int(re.sub(r"\D", "", r["post"]) or 0))
    write_log(rows)
    return [f"Logged {a.post.upper()} → {a.format}" + (f" (shaped as {a.shape})" if a.shape else "")]


def main():
    ap = argparse.ArgumentParser(description="Format Finder for @threelittlereaders.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("find")
    p.add_argument("--id")
    p.add_argument("--idea")
    p.add_argument("--pillar")
    p.add_argument("--child", choices=list(CHILDREN))
    p.add_argument("--message", choices=list(MESSAGES))
    p.add_argument("--goal", choices=list(GOALS))
    p.add_argument("--top", type=int, default=3)
    p = sub.add_parser("plan")
    p.add_argument("format")
    p.add_argument("--child", choices=list(CHILDREN))
    p = sub.add_parser("list")
    p.add_argument("--family", choices=["Challenge", "Storytelling", "Educational"])
    sub.add_parser("stats")
    p = sub.add_parser("log")
    p.add_argument("--post", required=True)
    p.add_argument("--format", required=True)
    p.add_argument("--shape")
    p.add_argument("--note")
    a = ap.parse_args()
    out = {"find": cmd_find, "plan": cmd_plan, "list": cmd_list, "stats": cmd_stats, "log": cmd_log}[a.cmd](a)
    print("\n".join(out))


if __name__ == "__main__":
    main()
