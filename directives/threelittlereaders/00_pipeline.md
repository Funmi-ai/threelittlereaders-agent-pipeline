# @threelittlereaders Content Pipeline (master SOP)

## Purpose
Every idea moves through the same team in the same order, from a rough line in chat to a posted reel or carousel and back into the Sunday review. Nobody needs the chat history: **the post file is the baton**. Each role reads its brief, writes its section, and moves the status on.

Cheap by design: roles read a context pack (`brief`), not whole files, and each stage can run in a fresh session.

## The team
| Role | Card | Runs as (model) | Owns |
|---|---|---|---|
| **Producer** | this file | the main chat, **Sonnet** (she sets it with `/model`) | Intake, routing, QA, tracker, logging, her sign-off |
| **Researcher** | `roles/researcher.md` | subagent `ig-researcher`, Sonnet | What works out there + what worked for us; Sunday review prep |
| **Hook Generator** | `roles/hook_generator.md` | subagent `ig-hook-generator`, **Opus** | Cover and first on-screen line |
| **Sally Filter** | `roles/sally_filter.md` | subagent `ig-sally-filter`, Sonnet | Sally's honest reaction to the hooks, then the caption — stop/skip, possibility/superiority, follow/not |
| **Copywriter** | `roles/copywriter.md` | subagent `ig-copywriter`, **Opus** | On-screen story, caption, Repurpose |
| **Designer** | `roles/designer.md` | subagent `ig-designer`, Sonnet | The visual system; reel covers; design QA on carousels |
| **Carousel Builder** | `roles/carousel_builder.md` | subagent `ig-carousel-builder`, Sonnet | Slide outline, then the Canva build |

**How the Producer delegates:** spawn the role's agent (`.claude/agents/ig-*.md`) with the post ID(s) and, for revisions, her notes verbatim. Each agent reads its card and its brief, writes only its own section of the post file, and returns a short summary. Subagents can't talk to her, so every pick and approval comes back through the Producer. Small fixes she asks for directly (one word, a sticker) the Producer can make itself; anything that's drafting goes to the agent.

Working as a role by hand (e.g. if agents aren't loaded): read its card, then run its brief. Don't read the reference files whole unless the brief says something is missing.
```
python3 execution/instagram_post.py brief --id IG-0xx --role researcher|hooks|sally|copy|design|carousel
```

## Where things live
- **Tracker** (`outputs/instagram/Instagram_Content_Tracker.xlsx`): one row per post, the test card, the status. Only ever written through `execution/instagram_write.py` (see `directives/instagram_content.md`). **`instagram_write.py patterns`** computes live structural patterns (question vs statement covers, length, etc.) against skip rate and follows/1k — the Hook Generator runs this before every batch of options (see its role card), so a recommendation is checked against real history every time, not just when someone remembers to look.
- **Post file** (`outputs/instagram/posts/week-of-<Mon>/<date>_<PILLAR>_<slug>.md`): the baton. Sections in order: Facts → Research note → Hooks → Sally check → Cover → On-screen story *or* Slides → Caption → Repurpose → Design & build → QA. The Sally check section is written to twice (after Hooks, then again after Caption), as dated entries in the same section. Created by `instagram_post.py new` (carousels get a Slides table, reels an On-screen story).
- **Repurpose log** (`outputs/instagram/repurpose_log.csv`): every Story and Threads post, logged with `execution/instagram_repurpose.py` (`story`, `threads`, `result`, `wins`).
- **Watch signals** (`outputs/instagram/signals/signals.csv`): the mums' own words from the ChatGPT watch, logged with `execution/instagram_signals.py add`. They reach the briefs automatically. See `watch_signals.md`.
- **Playbooks** (read through the brief, not directly): `outputs/instagram/audience_sally_2.md` (Sally; §6 grows from the watch), `audience_community.md` (the wider circle, for COMMUNITY/SHARE), `kids_and_approach_profile.md`, `canva_carousel_guide.md`, `Write In Voice/write-in-voice.yaml`, `execution/instagram_hooks.py`, the formula in `execution/instagram_post.py`.

## Status = the last stage finished
`Idea → Scheduled → Briefed → Hooked → Drafted → Built → Approved → Posted` (or `Skipped`)

Set with `instagram_write.py status --id IG-0xx --status Hooked`. **"What's stuck?" / "where's everything at?"** → `instagram_write.py pipeline` (open posts by stage, with whose move it is and ⚠ on anything due within a day).

## The flow
```
YOU ─► 0 INTAKE ─► 1 RESEARCH ─► 2 HOOKS ─► 2.5 SALLY CHECK (hooks) ─► ★ she picks
                                               │
                     REEL ◄────────────────────┴───────────────────► CAROUSEL
          3a Copywriter: story + caption                3b Builder: slide outline + caption
          3.5 SALLY CHECK (caption)                      3.5 SALLY CHECK (caption)
          4a Designer: cover                            4b Builder builds in Canva, Designer checks
                     └──────────────────────┬──────────────────────────────┘
                                   5 QA ─► ★ she approves ─► 6 PUBLISH & LOG ─► 7 SUNDAY REVIEW
                                                                                  │
                                         learnings go back into the playbooks ◄───┘
```

### 0 · Intake (Producer) → status Scheduled, then Briefed
1. She drops a rough line. Log the test card: `instagram_write.py idea --idea "…" --format … --pillar … --angle … --testing "…" --follow-reason "…"`. Read the date back.
2. `instagram_post.py new --id IG-0xx` to create the post file.
2b. **Decide what should be shown before asking about footage:** `instagram_formats.py find --id IG-0xx` (`directives/threelittlereaders/format_finder.md`). Put the ★ format's film plan in the intake message, so question 2 becomes "Here's what to film. Got something that fits, or will you film it to this?"
3. **Send the 7 intake questions in ONE message and wait** (standing rule; skip any already answered):
   1. Pillar + format (reel / carousel / still), and when it goes out?
   2. What's in the footage, in order, and how long? (none → carousel or staged b-roll?)
   3. Exactly what did the child do or say? Verbatim quote? What can / can't they do?
   4. When was it filmed? (affects "today" / "yesterday")
   5. Your angle or feeling: what changed for you, what was true?
   6. Anyone to tag or credit, and did they ask publicly?
   7. Any lines or phrasing of yours to keep?
4. Write her answers into **Facts**. Never invent details, feelings or times. New facts about the boys also go into `kids_and_approach_profile.md` (standing rule).
5. Researcher writes the note (stage 1), then set **Briefed**.

### 1 · Research (Researcher) · part of Briefed
Five lines in the post file: closest past post and how it did, the format (Format Finder ★, logged with `instagram_formats.py log`), the one thing it tests, a watch-out, the follow reason. See the card.

### 2 · Hooks (Hook Generator) → 2.5 Sally check → ★ she picks → Hooked
Three options, one starred with a one-line reason. Before she picks, the Sally Filter reads all three (per `roles/sally_filter.md`'s full review format) and appends a dated entry to **Sally check**: her first reaction, the Sally score, what's not working, and — since hooks are all that exist yet — its read on which option actually earns her thumb. She picks (from the options and the Sally read) or rewrites. Write `Picked:` and set **Hooked**.

### 3 · Copy → 3.5 Sally check → Drafted
In the same pass, the Copywriter fills the post file's **Repurpose** section: one Story frame + sticker, and two Threads lines (see below).
- **Reel:** Copywriter writes the cover (from the picked hook), the on-screen story and the caption.
- **Carousel:** Carousel Builder writes the slide outline; Copywriter writes the caption.

Once the caption's drafted, the Sally Filter reads the whole thing — cover, overlay, caption together — and appends a second dated entry to **Sally check**, per the card's iterative-edit rules (compare against its own first entry rather than redoing the full audit; call out what changed, not just re-score everything). Fix anything it flags before QA, not after.

### 4 · Design & build → Built
- **Reel:** Designer specifies the cover (frame or photo + text placement) in the house style.
- **Carousel:** Builder builds in Canva from the house template; Designer runs the design checklist. Canva edits and merges need her approval each time.

### 5 · QA (Producer) → Approved
1. `instagram_post.py check <file>`: fix every ✗.
2. Read through: every formula beat, line 1 gives nothing away, every claim about the child matches Facts, Sally check (possibility not superiority, nobody's approach knocked), nothing breaks the frequency test rules (in the researcher brief while the test runs).
3. Present the final version once. **Her standing instruction (19 Oct 2026): don't make her confirm/approve before she posts.** She's still in the loop on the creative calls as they come up (hooks, overlay wording, caption edits) — that's not what she's opting out of. What she's opting out of is a final "approve this before it goes out" checkpoint. So: present it, fix anything `check` actually flags, and move on — don't wait for a "yes, approved" reply. When she does edit something herself along the way, still log what's distinctly her in `Write In Voice/write-in-voice.yaml` → LEARNED FROM HER EDITS (standing rule). **Title Instagram entries with "Instagram"** so the briefs pick them up.
4. `instagram_write.py edit --id … --hook "…" --caption "<file>"`, then set **Approved**.

### 6 · Publish & log → Posted
She posts, in her own time, without a prior sign-off. **Don't wait to be told.** Run `python3 execution/instagram_sync.py` proactively (it matches a live post to its Content Plan row by link, then by posted date, and writes its metrics — see the script's own docstring) whenever it's reasonable she may have posted something: she mentions a post went up, a scheduled date/slot has passed, or at the start of a session touching this account. This replaces asking her to run `instagram_write.py posted --id … --link …` herself. When a Story or Threads post goes out, log it (one line, she can run it herself): `instagram_repurpose.py story --post IG-0xx` / `threads --post IG-0xx --text "…"`.

### 7 · Sunday review (Researcher)
Follow the Sunday loop in `directives/instagram_content.md` (sync, screenshots, verdicts, remix Wins, next 7 days). Then **close the loop**: every learning goes into the playbook it belongs to (see the Researcher card). This is how the team gets better.

## The Repurpose arm: Stories and Threads
Two side channels with different jobs. Every post file has a Repurpose section, filled in the same Copywriter pass from the same brief (no extra brief, no extra session).
| | Stories | Threads |
|---|---|---|
| Audience | Followers | Strangers who read |
| Job | Keep followers close, and collect their words | A free test bench for hooks before spending footage on them |
| What goes there | Outtakes, the reel reshare, a question box or poll | The hooks she didn't pick (with a one-line payoff, since there's no video) and the caption's best paragraph |
| What comes back | Question-box answers → `instagram_signals.py add` (source: `our story RP-…`), first-party Sally language | Replies and views → `instagram_repurpose.py result`; `wins` at the Sunday review → evidence in `instagram_hooks.py`, then reel hooks |

- **Stories are posted whenever there's something worth posting**, never held back. Log each Story day; the frequency-test review shows how Story days fell across single and double days and warns if they're lopsided.
- **Stickers are soft and short:** 22 characters max (emoji aside), because the question box cuts the prompt off past that (`check` flags longer ones).
- A Threads win is a reason to try the hook on a reel, not proof: Threads readers aren't Sally.
- **Threads isn't launched yet** (her call, 4 Oct: waiting for more content first). Keep filling the Threads lines anyway; they bank up in the post files, so launch day starts with a backlog of ready posts.
- No API for either yet (Threads needs its own app setup; Story insights vanish after 24h). Threads numbers are read by hand at the Sunday review; Stories aren't measured, only harvested for words.

## The fast lane: the daily lunchtime vlog (START video, Lunch slot)
Skip research and design, **never the hooks**: the cover and overlay are what earn the view. Intake (questions 2–5 only) → Hook Generator (3 cover + overlay options, ★ one, she picks) → Copywriter writes story and caption → QA → her approval. If she brings her own draft, her cover and overlay are option 1 and the Hook Generator still offers two alternatives. `pipeline` labels these posts "fast lane".

## Cost rules (keep every stage cheap)
1. **Brief, don't browse.** Each role runs its `brief` and reads its card. Opening a whole playbook is the exception, and only for the section the brief lacks.
2. **Fresh session per stage.** The post file carries everything forward, so `/clear` between stages loses nothing. Long sessions re-send their whole history every turn.
3. **Batch by stage, not by post.** Hooks for the whole week in one sitting, then copy for the whole week. The card and reference material load once.
4. **Model by role:** the main chat runs on Sonnet; hooks and copy run as Opus subagents; Researcher, Designer and Carousel Builder run as Sonnet subagents. Fable only at the review checkpoints (22 Oct, ~15 Nov, ~15 Dec), set by her with `/model`. Claude can't change its own session's model; it picks the model by choosing which agent to hand to.
5. **Cap output:** three hooks, one-line reasons. One draft, then edit from her notes; never regenerate from scratch.
6. **Agents start cold, and that's fine:** the brief packs keep each one to roughly 2k–8k tokens of reading. Batch a week's posts into one agent call where possible (hooks for the week, then copy for the week).

## Learnings
- 2026-10-26: **Format Finder** added (`execution/instagram_formats.py`, SOP `format_finder.md`), her direction: "it's not about what I want to show, it's about what should be shown, and then do that." The format is now decided at intake, from the post's message and goal plus our own results, before footage is discussed. The Researcher's brief carries the ranking, and the hooks, copy and carousel briefs carry the picked format's film plan. 32 past posts were backfilled in `outputs/instagram/format_log.csv`.
- 2026-10-19: bug fixed — `instagram_post.py`'s `post_path()` recomputes a post's file path from the tracker's *current* idea text and pillar every time it's called. Editing either after the file already exists (e.g. correcting a stale idea string, or changing pillar/angle) silently makes every later `brief`/`new` call compute a *different* path than the real file on disk, so `brief` reported "Post file: not created yet" for a file that existed (hit on IG-032, after its idea text and pillar were both edited post-creation). Fixed by adding `find_existing_post_file(post_id)`, which finds the real file by its title line's `· IG-0xx` marker; `brief` now tries that before falling back to the computed path, and `new` refuses to spawn an orphaned duplicate at the new computed path if one already exists elsewhere under the old one. Takeaway: editing a post's idea/pillar in the tracker after its file exists is safe again; the file itself is still never renamed (cosmetic only).
- 2026-10-19: Sally Filter role added (`ig-sally-filter`, Sonnet), her instruction verbatim: "include a sally filter agent who reads everything written by hook generator, me or editor and evaluates as a mum scrolling through after bedtime — let's really make sure the sally filter is a close match to sally." Runs twice per post, same brief command (`--role sally`), appending two dated entries to one **Sally check** section: after Hooks, before she picks; after Copy, before QA. Formalises what was previously informal (the Producer's own "Sally critique mode" on her rewrites, and the single "Sally check" line at the end of `check`'s manual checklist) into a written, every-post step. First use: IG-032.
- 2026-10-19 (same day, expanded): she replaced the role's instructions wholesale with a full "Sally Filter — Audience-First Content Editor" spec (pasted verbatim into `roles/sally_filter.md`): embodied first-person Sally reaction, a scored 8-criteria/40-point audience-value rubric, a 9-part response format (reaction, actual value, score, what's not working, strongest angle, 3 ranked hooks, a full recommended edit/storyboard/caption, a stress test, and a PUBLISH/REVISE/REPOSITION/HOLD verdict), and iterative-edit rules for re-review. The two checkpoints (after Hooks, after Copy) and the single `Sally check` section stayed the same — only what the role writes there got much deeper. Note: the new spec's §1 says "Sally is a UK mum"; flagged against `audience_sally_2.md` §1's "don't narrow to UK". Settled same day, after she went back and forth: international stays (a UK affiliate layer can sit on top of specific posts/links later without redefining who Sally is) — `audience_sally_2.md` §1 updated to record the back-and-forth; the role card's §1 line is now superseded by it.
- 2026-10-04: results now feed the Hook Generator directly: "Hooks that held" in the hooks brief (skip rate + watch time from the sync, by slot). Results reach the Researcher through "Nearest evidence", and the Copywriter only through the weekly formula updates (a judgement call, kept manual).
- 2026-10-04: roles became agents with fixed models (`.claude/agents/ig-*.md`): Opus where her voice shows (hooks, copy), Sonnet for everything else, main chat on Sonnet. Possible now because the briefs make a cold start cheap.
- 2026-10-04: Repurpose arm built (Stories + Threads). Her call on the frequency test: she won't hold back Stories on days she has something to post, so instead of a rule, Story days are logged and the review shows the split. First use: the Day 8 singing outtake as a Story ("Meanwhile, on backing vocals…").
- 2026-10-04: first real run (IG-021, Day 8 vlog, fast lane, her ChatGPT draft). The copy brief caught two things a whole-file skim would have missed: (1) the vlog numbering rule (Day 8 is right despite the 2 Oct "Day 8 recap" label), and (2) an accuracy risk: letter-name songs (BINGO, A E I O U) against "never taught letter names, knows letters only as sounds". When she brings a ChatGPT draft, the Copywriter's job is a minimal pass (voice rules, check, facts), not a rewrite, and her original goes verbatim at the bottom of the post file. `new` now skips the Research / Design sections for fast-lane posts. **Correction (same day, her feedback):** the fast lane first skipped the Hook Generator too, and she noticed nobody had offered a better cover or overlay. Hooks are never skipped; they're the cheapest stage with the biggest effect on views.
- 2026-10-04: pipeline created. Roles became cards plus `brief` packs (copy ~16KB ≈ 4k tokens, design ~4KB) instead of reading ~92KB of playbooks per post. The voice digest is read live from the voice file by `brief`, so there's no separate digest file to go stale. Tracker statuses gained Briefed / Hooked / Built / Approved (migrated; backup `backups/pre-pipeline_…`). `instagram_post_writing.md` was split into the role cards.
- 2026-10-27: **Sally bar = 37/40** (her rule: "we should always be aiming for 37/40"). Nothing is presented to her as ready below 37 unless Sally says the footage or facts cap it. In that case, show her the score and the cap, and she decides.
