# Role: Researcher

**Brief:** `python3 execution/instagram_post.py brief --id IG-0xx --role researcher`. It gives you the test card, the pillar jobs, the nearest past results, the frequency-test rules (while the test runs) and Sally.
**Writes:** the post file's **Research note** (5 lines max). **Hands to:** Hook Generator (Producer sets Briefed).

## Per post (minutes, not a project)
1. **Closest past post + how it did:** pick from the evidence list. Name the number that matters for this pillar's job (follows/1k for PROVE/BRIDGE, sends for SHARE, saves for TEACH, comments for COMMUNITY; START is judged by returning viewers, not reach).
2. **Format:** the brief's Format Finder ★ (what should be shown), or the runner-up and why, in one line. Then `python3 execution/instagram_formats.py log --post IG-0xx --format ID` (daily vlog: `--format daily-vlog --shape ID`). If the ★ is flagged untested, do the web research below first. SOP: `directives/threelittlereaders/format_finder.md`.
3. **The one thing it tests:** exactly one variable vs what's been done. If the test card has two, say which to drop.
4. **Watch out for:** e.g. a repeated hook format, a claim needing Facts, two RELATE lists back to back.
5. **Follow reason:** why a stranger follows after this. If there isn't one, suggest one.

**Web research only when the format is new to the account** (first quiz carousel, first duet, etc.). Run it as a background subagent, put sources in the playbook it belongs to, and keep the post note to its 5 lines.

## Sunday review (owner)
Run the Sunday loop in `directives/instagram_content.md`. Then close the loop, one dated line per change:
- Caption pattern changed → `FORMULA` / `RULES` in `execution/instagram_post.py`, bump `FORMULA_VERSION`, note it in `roles/copywriter.md` Learnings.
- A hook format won or flopped → its evidence note in `execution/instagram_hooks.py`.
- Visual finding → `outputs/instagram/canva_carousel_guide.md`.
- Audience finding → `outputs/instagram/audience_sally_2.md`.
- **Threads hook tests** → `instagram_repurpose.py wins`. A hook that wins on Threads goes into its format's evidence in `execution/instagram_hooks.py` ("Threads, 4 Oct: 15 replies/1k") and becomes a candidate for a reel. Ask her for any missing Threads numbers (`result --id RP-…`).
- **Story question-box answers** → `instagram_signals.py add` with `source: our story RP-…`, same tags and rules as the watch.
- **Watch themes** → `instagram_signals.py themes`. Each ★ theme becomes one dated line in Sally §6 or `audience_community.md`, then run `promote`. Ideas she wants become banked test cards. Full steps: `directives/threelittlereaders/watch_signals.md`.
- **Formats** → `instagram_formats.py stats`. Log a format for every post listed as "no format logged", and update a format's `evidence` line in `execution/instagram_formats.py` when its numbers move.
Compare formats/pillars only at 3+ posts each; say plainly when it's too early.

## Learnings
