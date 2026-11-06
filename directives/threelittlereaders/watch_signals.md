# Watch Signals: the mums' words, from ChatGPT into the pipeline

## Purpose
A scheduled agent in ChatGPT watches online conversations from parents about early reading: how they talk and what they fear. Loose ideation stays in ChatGPT, which saves Claude usage. Only the lines she chooses to keep come here, in a fixed format, so logging them is a script run with no model reasoning needed.

Raw reports are never stored here.

## The flow
1. The ChatGPT report ends with a **FOR CLAUDE** block (format below).
2. She copies only the lines worth keeping.
3. She runs `python3 execution/instagram_signals.py add` herself in the terminal (it reads the clipboard), or says "log signals" and Claude runs it. Either way it costs no thinking: one command and a short printout.
4. From then on, automatically:
   - **Hooks and copy briefs** show the newest Sally phrases ("her words right now"), plus the unused hook seeds for the Hook Generator. COMMUNITY/SHARE posts also get the wider-circle phrases and `audience_community.md`.
   - **Researcher brief** shows the themes, with ★ on themes ready to promote, and unused ideas from the watch.
5. **Sunday review (Researcher):** run `instagram_signals.py themes`. For each ★ theme, write one dated line into **Sally §6** (`who: sally`) or **audience_community.md** (`who: wider`): the phrase, what's underneath, and what it means for content. Then run `promote --tag … --to sally|community`. Ideas she wants become test cards (`instagram_write.py idea … --unscheduled`), and their signal is marked with `use --id SIG-… --post IG-…`.

## Rules
- **Language moves fast, persona moves slowly.** Phrases reach the briefs the day they're logged. Sally and the community profile only change when a theme repeats: 2+ separate reports or 3+ signals.
- **Hook seeds from the watch are raw material.** They're linted on entry, and failures are flagged ✗ in the briefs. The Hook Generator rewrites them in her voice. Never post one as-is.
- **Privacy:** these are real parents. Use the patterns in their language, never quote anyone identifiably, never link or screenshot their post, and never reply to them as the brand from a signal. Source links stay in the private log.
- **Every signal needs a source link and date** so it can be checked. `add` flags any line without one. First-party sources don't need a link: `source: our story RP-…`, `our comments IG-…`, `our dms` (answers from her own Stories, comments and DMs are the best evidence of all, and the same privacy rules apply).

## Paste this into the ChatGPT agent's instructions
```
At the end of every report, add a block headed === FOR CLAUDE === with one line per item, in exactly this format (no other text in the block):

SIGNAL | who: sally | stage: reception | tag: doing-enough | phrase: "their exact words, max 20 words" | underneath: what they're really asking, one sentence | source: https://full-link | seen: YYYY-MM-DD
HOOK | for: sally | text: a hook idea
IDEA | for: sally | text: a content idea in one line

who: sally = a parent of a 2–7 year old who wants to help but worries she doesn't know enough or isn't doing enough. wider = any other parent (child already ahead, comparing school schemes, older kids, etc.).
stage: baby | toddler | preschool | reception | ks1 | mixed
tag (exactly one, from this list only): behind, comparison, doing-enough, pushing-too-hard, wrong-method, wrong-order, needs-curriculum, too-early, too-late, no-time, knowledge-gap, play-enough, child-resists, school-vs-home, buying-stuff, ahead-what-next, want-love-of-reading, want-independence, want-practical-how
phrase: the parent's own words, verbatim, in quotes. seen: the date of the original post, not today.
HOOK lines must avoid: "Here's what…", "actually", opening with "If you…" or "Sometimes", "It's not X, it's Y", em dashes, and the words ship, unlock, leverage, magic, hack, secret, transform, curious, messy. Use British spelling.
```

## Learnings
- 2026-10-04: set up. The first report logged was the "Reception turns phonics into a comparison problem" report (two Reddit posts, no links given). 2 of its 5 suggested hooks failed the voice lint ("Here's what… actually", "If you only managed…"), which is why the format above lists the rules.
