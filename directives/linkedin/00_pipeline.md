# LinkedIn Arm Pipeline (master SOP)

## Purpose
Every lead magnet gets one companion LinkedIn post. Every real proof point from the build (a finding, a fixed mistake, a number) is a candidate for one too. The post's job is never to pitch: it documents something true and lets the capability speak for itself, the way week 2's "watch as I grow" post did ("Who comes back is the question I help marketing teams answer every day through lifecycle marketing").

**Standing trigger (set 4 Oct 2026):** the moment a lead magnet is published (an Artifact, a PDF, a Canva design, a Claude Doc), log it and start this pipeline. Don't wait to be asked.

## The team
| Role | Card | Runs as (model) | Owns |
|---|---|---|---|
| **Producer** | this file | the main chat | Trigger, logging, QA, her sign-off |
| **Researcher** | `roles/researcher.md` | subagent `li-researcher`, Sonnet | The one true moment + real numbers |
| **Hook Generator** | `roles/hook_generator.md` | subagent `li-hook-generator`, **Opus** | 3–5 hooks, formula-labelled |
| **Copywriter** | `roles/copywriter.md` | subagent `li-copywriter`, **Opus** | The full post, in her voice |
| **Offer Strategist** | `roles/offer_strategist.md` | subagent `li-offer-strategist`, **Opus** | The bridge line + the CTA call |
| **Visual Designer** | `roles/visual_designer.md` | subagent `li-visual-designer`, Sonnet | The accompanying card image |

Same relay-baton shape as the Instagram pipeline (`directives/threelittlereaders/00_pipeline.md`): one file per post, each role reads its card + the file, writes its own section, hands it on. She's needed at three points: confirming the real moment with Researcher, picking a hook, and final approval.

## Where things live
- **Pairing log:** `lead-magnets/lead-magnet-post-log.md`. One row per lead magnet: what it is, its link, the companion post's status.
- **Post file:** `lead-magnets/linkedin-watch-as-i-grow/posts/<slug>.md` (parenting-angle / dual-track posts) or alongside the lead magnet itself for a pure service post. Sections: Source → Hooks → Draft → Bridge & CTA → Visual → QA → FINAL.
- **Visuals:** `lead-magnets/linkedin-watch-as-i-grow/visuals/`, built per `directives/export_linkedin_image.md`.
- **Voice:** `Write In Voice/write-in-voice.yaml` (the whole file applies; REGISTER, PARENTHETICAL SOFTENERS, ENDINGS, ICP PROBLEM and DM/OUTREACH CALIBRATION matter most here) + CLAUDE.md's Fattima's Voice Guidelines (always in context already).
- **Hooks:** `.claude/skills/hook-generator.yaml`, the 9 formulas + hard nos.

## The flow
```
Lead magnet published ──► 0 LOG ──► 1 RESEARCH (★ she confirms the moment)
                                                │
                                        2 HOOKS ──► ★ she picks
                                                │
                                        3 COPY (full post, her voice)
                                                │
                              4 BRIDGE & CTA (Offer Strategist)
                                                │
                                        5 VISUAL (the card)
                                                │
                              6 QA ──► ★ she approves ──► 7 PUBLISH & LOG
```

### 0 · Trigger & log (Producer)
On publishing any lead magnet: add a row to the pairing log, create the post file, and start stage 1. Say plainly that a companion post is starting, don't wait to be asked twice.

### 1 · Research (Researcher)
Pull **one real moment** (with dialogue, if there was any) and the real numbers behind it, from the lead magnet itself, the tracker, or this session's own build. Say which track it serves: parenting (the account itself), proof-of-build (the system behind it), or both, the way every "watch as I grow" post so far has been. **★ Confirm the moment with her before anyone writes a line** — her standing rule (`feedback_post_questions_first`) applies here as much as it does on Instagram.

### 2 · Hooks (Hook Generator) → ★ she picks
3–5 options from `hook-generator.yaml`, each labelled with its formula. Parenting moments default to formula 0 (indefensible claim) or 8 (verbatim kid quote); proof-of-build moments default to formula 3 (contrarian observation) or 6 (contrast journey) — the shape of "My best Instagram post had one of the worst engagement rates on my account."

### 3 · Copy (Copywriter)
The full post in her actual rhythm: flowing sentences that set the scene, one real moment with tension, parenthetical softeners, ends on wisdom. Conversation, never a diary update. See the card for the accuracy rule (never "every"/"all" when the system doesn't do that) and the structures she's rejected before (no scene from the other audience grafted in, no bracketed "relatable filter" rewrite).

### 4 · Bridge & CTA (Offer Strategist)
Reads the drafted post and decides: does it earn one bridge line to the professional capability (like week 2's lifecycle-marketing line), and if so, writes it. Decides the CTA, if any: a link (only once there's real data behind it — the case-study link is on hold for exactly this reason), a comment-to-DM prompt, or nothing this time. **No pitch, ever** — if the post has no honest bridge, it runs without one.

### 5 · Visual (Visual Designer)
One card per post (occasionally two), per `directives/export_linkedin_image.md`: Fatz brand colours, safe zones, exported with capture-website-cli.

### 6 · QA (Producer) → ★ she approves
Check against CLAUDE.md's voice guidelines and `hook-generator.yaml`'s hard nos (banned words, "Here's the truth no one tells you", "It's not X, it's Y", anything that reads as engagement bait). Check every number against its source. Present it whole: hook, post, visual, bridge line, proposed CTA.

### 7 · Publish & log
She posts. Mark the pairing log's row Posted, with the link.

## Cost rules
Same philosophy as the Instagram pipeline, adjusted for lower volume (roughly one post per lead magnet, not daily): fresh thread per stage where it's a long one, Opus only where voice or commercial judgement shows (hooks, copy, the bridge line), Sonnet for research and the visual export. No tailored context-pack script yet — the files here are already small enough to read directly; revisit if volume grows.

## Learnings
- 2026-10-04: built, after "From Scattered Files to a Content Pipeline" (the IG-pipeline lead magnet) went up with no companion post queued. That gap is what the pairing log and the stage-0 trigger are for.
