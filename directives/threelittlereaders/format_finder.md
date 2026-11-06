# Format Finder (@threelittlereaders)

## Purpose
Decide **what should be shown** for a post before anything is filmed or cut, then film to that plan. The starting question isn't "what footage have I got?" but "what video would best prove this post's point to Sally?" Once that's decided, she films it.

Built 26 Oct 2026, modelled on OnePeak Creative's Format Finder (formatfinder.onepeakcreative.com, $29–97/mo). Theirs: a niche goes in, and out comes a library of 65+ named formats (Challenge / Storytelling / Educational) → hook → script → shot list, plus an editor and drop-off analysis. Ours keeps the useful part, the named, repeatable formats, rebuilt for a parent-confidence early-reading account. It ranks them against **this account's own results** instead of marketing claims. We skip their editor (she uses Edits / CapCut) and their per-second retention (the Instagram API only gives skip rate and average watch time).

## Tool
`execution/instagram_formats.py`, with the log in `outputs/instagram/format_log.csv` (one row per post: format, plus the shape a daily vlog was cut as).

| Command | When |
|---|---|
| `find --id IG-0xx` | Intake, before asking about footage. Ranks the formats for this post, stars the best and prints its film plan |
| `find --idea "…" --pillar PROVE` | A loose idea that isn't in the tracker yet |
| `plan FORMAT [--child middle]` | The film plan for one format (beats with seconds, overlay jobs, shot list, paired hooks) |
| `log --post IG-0xx --format ID [--shape ID]` | As soon as a format is picked. Daily vlogs: `--format daily-vlog --shape <format>` |
| `stats` | Sunday review: each format's reach, skip and follows/1k, what hasn't been tried, and posts with no format logged |
| `list` | Browse the 21 formats |

## How it decides (all shown in the output, nothing hidden)
1. **The moment** (+5): the idea text describes this format's kind of moment (an arrow chain → word chain, "every 'no'" → blooper montage, "couldn't… callback" → couldn't-then-could).
2. **The message** (×3): what the post must make Sally believe: `possible`, `method`, `permission`, `relatable`, `progress`, `everywhere`, `real`, `conversation` or `myth`. It's read from cue words; when none match, it falls back to the pillar's default at half weight. Override with `--message` when the cues miss.
3. **The goal** (×3): the pillar's job (PROVE / BRIDGE / RELATE → follow, TEACH → save, SHARE → share, COMMUNITY → comment, START → watch). Override with `--goal`.
4. **Pillar** (+1), **child** (−3 if the format can't show the post's child), **our results** (+1.5 / −1 against the account median on the goal's metric; rates built on fewer than 3 actions don't count), **recency** (−1.5 if the same format ran in the last 5 days).

The fast-lane daily vlog keeps its fixed format and opener; the finder only picks its **shape** (everyday-spot, couldn't-then-could, mystery bag…).

## Flow
1. **Intake (Producer):** after `instagram_post.py new`, run `find --id`. Put the ★ format's film plan in the single intake message, so question 2 becomes "Here's what to film. Already got something that fits, or will you film it to this?" (one message, standing rule).
2. **Research (Researcher):** the brief includes the finder output. Write the Format line: the ★ format, or the runner-up and why, in one line. Then `log` it. If the ★ is flagged untested, do the web research first, per the role card.
3. **Hooks / copy / carousel:** their briefs carry the logged format's film plan. Hooks start from its paired hook IDs; the on-screen story follows its beats.
4. **Sunday review:** `stats`, log a format for anything posted without one, and update a format's `evidence` line in the script when its numbers move.

## Edge cases
- **Footage already exists** (e.g. a filmed word chain): the finder still decides. When the ★ format needs a shot that doesn't exist (a "then" clip, a set-up shot), the plan says so. Film the one missing clip rather than bending the format.
- **A different child would show it better:** the child penalty flags it. Her moment stays her moment; never swap the child on a real event.
- **Untested formats** (play-along, mystery bag, he-quizzes-me, which-book-wins, then-vs-now, myth-check, consequence-skit) can win on fit alone. The output warns, and the first one of each is a test: one variable, judged at the Sunday review.
- **Never invent the moment** a format needs. A skit re-creates something that really happens; a challenge only uses words he's genuinely attempting.

## Learnings
- 2026-10-26: built. 32 posted posts backfilled. First read (`stats`): word chains lead (3 posts, 1,818 avg reach, 3.7 follows/1k). Plan-vs-reality vlogs average 48% skip; IG-080, a refusal with no turn, hit 64%. Everyday-spot vlogs hold best among the vlog shapes (31% skip, 5 posts). To-the-mum still converts (2.4 follows/1k) despite weaker reach. Early signals, under 5 posts each.
- 2026-10-26: early tuning showed message cues alone misfire ("game" → method sent a word chain to a carousel). What the moment *is* now leads (+5), and a pillar-default message only counts half.
