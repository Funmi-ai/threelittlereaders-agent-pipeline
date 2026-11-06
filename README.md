# threelittlereaders-agent-pipeline

A 12-agent Claude Code system that runs two live content pipelines end to end: the [@threelittlereaders](https://instagram.com/threelittlereaders) Instagram account, and its companion LinkedIn arm. Each agent has one job, a model picked for what that job needs, and a shared file it hands work forward through, like a relay baton.

This is the actual system in production, with the account's personal data (trackers, audience research, real posts) stripped out — what's here is the architecture, the agent definitions, and the deterministic scripts underneath them.

## Why it's built this way

LLMs are probabilistic. Most of the work around them — scoring, logging, file writes, API calls — isn't, and shouldn't be treated like it is. Chaining five steps at 90% reliability each only compounds to about 59% success end to end. So the system pushes everything repeatable into deterministic code, and keeps the model's job to the calls that actually need judgement.

Three layers, used by every agent here:

1. **Directive** (`directives/`) — an SOP in Markdown: the goal, the inputs, which tools to use, what counts as an edge case. Written like a brief to a capable employee, not a prompt.
2. **Orchestration** (`agents/`) — the agent itself. Reads its directive, routes to the right script, handles errors, and hands anything that needs a real decision back to a person.
3. **Execution** (`execution/`) — plain Python underneath: the API calls, the scoring, the file writes. The same every time it runs.

## The two pipelines

### Instagram — 7 agents
One post file carries the work from a rough line in chat to a published reel or carousel, and back into the Sunday review.

```
Intake → Research → Hooks → Audience check → ★ pick → Copy/Build → Audience check → Design & QA → ★ publish → Sunday review
```

| Agent | Model | Owns |
|---|---|---|
| `ig-researcher` | Sonnet | Research note per post; scouts a format when it's new; preps the Sunday review |
| `ig-hook-generator` | Opus | 3 cover + first-overlay options, one starred |
| `ig-sally-filter` | Sonnet | Plays the audience: scored rubric, ranked hooks, a publish/revise/reposition/hold verdict |
| `ig-copywriter` | Opus | On-screen story, caption, and the repurpose lines (Story, Threads) |
| `ig-carousel-builder` | Sonnet | Slide outline, then the Canva build (clones one good page rather than starting blank) |
| `ig-designer` | Sonnet | Reel cover spec; design QA on built carousels |
| `ig-format-analyst` | Sonnet | Reverse-engineers niche outlier videos into formats worth testing |

### LinkedIn — 5 agents
Triggered whenever a real finding from the build — a lead magnet, a mistake, a number — is worth writing up.

```
Trigger & log → ★ confirm moment → Hooks → ★ pick → Copy → Bridge & CTA → Visual → ★ approve → Publish
```

| Agent | Model | Owns |
|---|---|---|
| `li-researcher` | Sonnet | The one real moment + real numbers behind a post |
| `li-hook-generator` | Opus | 3–5 hooks from a formula library, each labelled |
| `li-copywriter` | Opus | The full post, in voice, from the confirmed moment and picked hook |
| `li-offer-strategist` | Opus | Decides if the post earns a bridge line to the paid offer, and the CTA — no pitch if it hasn't |
| `li-visual-designer` | Sonnet | The accompanying brand card image, exported |

**Model allocation is deliberate, not default.** Opus runs only where the account's actual voice is on the line — hooks and copy, 5 roles across both pipelines. Every research, audience-check, QA and design pass runs on Sonnet. The model is chosen for the job, not the other way round.

## What holds the relay together

- **The baton** — one file per post carries every stage's output forward. No agent needs the chat history, so any stage can run cold, in its own session.
- **The status ladder** — a post's status is just the name of the last stage finished (`Idea → Scheduled → Briefed → Hooked → Drafted → Built → Approved → Posted`). One command answers "what's stuck?" for the whole pipeline.
- **Self-annealing** — when a step breaks (a rate limit, a missing field), the fix goes back into the directive, not just the code, so the next run starts already knowing what the last one learned.

## Structure

```
agents/        Claude Code subagent definitions (the orchestration layer)
directives/    The SOPs each agent reads before it does anything
execution/     The deterministic Python underneath — trackers, scoring, API sync, PDF/report generation
```

## Running it

The scripts expect a `.env` with `ANTHROPIC_API_KEY`, `AIRTABLE_API_KEY` and `INSTAGRAM_ACCESS_TOKEN` (none of which are in this repo). The data files these scripts read and write — the content tracker, audience research, post history — are intentionally not included; this repo is the system, not the account's data.

```
python -m execution.instagram_post brief --id IG-001 --role researcher
```

Agents are invoked through Claude Code by reading `agents/<name>.md` plus the directive it points to.
