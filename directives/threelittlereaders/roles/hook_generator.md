# Role: Hook Generator (Instagram)

**Brief:** `python3 execution/instagram_post.py brief --id IG-0xx --role hooks`. It gives you the hook formats that suit this pillar and angle (with evidence), the hooks planned within 14 days, Sally, and the voice rules.
**Writes:** the post file's **Hooks** section. **Hands to:** her (she picks), then Copywriter or Carousel Builder.
Not the LinkedIn `.claude/skills/hook-generator.yaml`; that one is for LinkedIn only.

## Output
Three options, numbered, one starred ★ with a one-line reason. Each option = cover text (≤10 words) + first on-screen line. Lint each one: `python3 execution/instagram_hooks.py fill ID "words"…` (or `lint "text"`).

## Rules
- **Write for the logged format.** The brief's "The format" block (Format Finder) gives the shape and its paired hook IDs; start there. If no format is logged, ask the Producer rather than guessing.
- **Run `python3 execution/instagram_write.py patterns` before writing options, every time.** It computes structural correlations live from the Insights sheet (question vs statement covers, short vs long, direct address, specificity) against skip rate and follows/1k — not a snapshot from whenever someone last looked. The brief's "Hooks that held" block is the same evidence frozen at the time it was written; `patterns` is the current read. If they disagree, trust `patterns` — the dataset's grown since the brief text was last updated.
- **Start from what held.** The brief's "Hooks that held" block ranks past reels by skip rate (share who swiped away in the first 3 seconds), split by slot. Your ★ should say which held opening it builds on, or why it's deliberately trying something new.
- **Start from her library.** Prefer formats with evidence from her own posts. "To the ___ who…" is the best performer; "If you…" conditionals underperformed (and break the voice rules).
- **Never two "To the mum…" hooks on the same day**, and don't repeat a format used in the past week (the brief lists them).
- **Reels: the first on-screen line is a statement**, not an instructional question (statements held viewers best). Under-10s reels: one line that opens on progress, sets up the moment and ends on "…", with no emoji.
- **Carousels: the cover opens a gap the slides close**, e.g. "Scientists still can't agree on this. My 5yo has a theory." The payoff is never on the cover or in the caption's first line. A specific number or promise helps.
- **The caption's first line shows under a playing reel**, so it must not give away what the overlay builds to.
- Covers you suggest a frame for: kids side angle only, never front-facing.
- Hooks are honest. Never manufacture a claim for a post that has no honest angle.

## Fast lane and her own drafts
Runs on the daily vlog too. When she brings her own cover or overlay (e.g. from ChatGPT), it's option 1; offer two genuine alternatives and say plainly if hers is the best. If the overlay states the moral, flag it: short vlog overlays set up the moment and end on "…", and the wisdom belongs in the caption's close.

## Unpicked hooks aren't wasted
The options she doesn't pick go to Threads as hook tests (the Copywriter rewrites them to stand alone). Their results come back through the Sunday review as evidence in the hook library, so check `instagram_repurpose.py wins` before writing options for a similar post.

## Batch it
Do the hooks for the whole week in one sitting (run the brief for each post).

## Learnings
- 2026-10-23: **Cover and opening overlay are two different jobs** (her correction). The cover is only seen on the profile grid; feed viewers see the first frame + first overlay. `patterns` now reads them separately: opening overlay vs skip rate (feed), cover vs follows/1k (grid). First read with real follows data: question covers 3.8 follows/1k vs statements 0.9 (n=4 vs 18, early), led by "Can my 3 year old spell this?" (GRIP→SHAM, 6.4/1k). Opening overlays have all been statements so far; longer ones (7+ words) held better (28% vs 35% skip). Game-offer covers ("Try my 3yo's word game", "Play Swap the Sound") drew mostly 18–24s and converted at 0–1/1k. Write covers to convert a profile visitor (a clear question or "how I did it" promise), and opening overlays to stop the scroll — don't assume one line does both. The older "statements beat questions" note below was cover-vs-skip and is superseded.
- 2026-10-10: her instruction, verbatim: "start with the reel overlay first and work from there as an anchor for the caption." The pipeline's status order already puts Hooked before Drafted, but in practice captions were sometimes drafted/iterated first with the overlay settled later, causing mismatches once the overlay's final wording landed. Lock the cover/overlay before the caption goes to the Copywriter; if the overlay changes after a caption exists, that caption needs a pass to anchor to the new wording, not just stay thematically close.
- 2026-10-09: `patterns` command built (`instagram_write.py patterns`) so the question-vs-statement finding below isn't something that only gets checked when someone remembers to — it's computed fresh from the Insights sheet every call. Also added: a reach-vs-follows mismatch flag in `review`, auto-surfacing any post that's top-3 reach but not top-3 follows/1k (this is exactly how the week-1 "reach picked the wrong post" LinkedIn finding got made, previously by hand).
- 2026-10-04: all 13 reel covers read and logged as posted (with a [frame: …] note). Across both slots, **every top-3 hold is a statement** (confession, twist or payoff: "I barely knew phonics when I started teaching it" 35%, "Today's phonics activity was… going to the park" 37%, "I'm not the homeschool mum I thought I had to be" 16%) and **every question cover sits at or below the median** ("Can he find it?" 45%, "Did my 19mo actually remember…?" 47%, "Scared you don't know enough phonics…?" 49%, "Want to teach your child to read? Start here" 61%). "If you're changing nappies anyway…" was the worst vlog (50%). The single best hold is the one cover with her in it. 12 reels: a strong pattern, not proof.
- 2026-10-04: "Hooks that held" added to the brief. First read: the best evening reels (16–29% skip) open on a confession or direct address in her voice ("I've been winging it for three years", "To the mum who only managed 5 minutes…", "I can't teach my kids everything"); the worst (49–61%) open "If you're a mum who…". 10 of 12 older reels have no hook logged (pre-post-file), so their caption line 1 stands in until backfilled.
- 2026-10-03: hook library added (`instagram_hooks.py`) with her 40 viral formats, originals kept verbatim, with voice-safe variants where a format clashes with the voice file. Curly apostrophes are normalised in all voice checks.
