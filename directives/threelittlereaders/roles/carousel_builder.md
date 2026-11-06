# Role: Carousel Builder

**Brief:** `python3 execution/instagram_post.py brief --id IG-0xx --role carousel`. It gives you the canvas, type sizes, structure, 2026 carousel nuances and the palette.
**Writes:** the post file's **Slides** table, then the Canva link in **Design & build**. **Hands to:** Copywriter (caption) after the outline; Designer (checklist) after the build.

## 1 · Outline (status Hooked → Drafted)
- 7–10 slides, about 25 words each (`check` flags anything over 30). One self-contained idea per slide.
- Slide 1 = the picked hook, opening a gap; small "→" swipe cue on slide 1 only.
- **Slide 2 must work as a cold first impression** (Instagram re-serves posts from slide 2).
- A surprising or contrarian slide around slides 4–5.
- Last slide: ONE ask (save, share, follow or comment), styled like the cover.
- Mix in at least one real photo (hands, objects, the table). Note it in the Visual column.

## 2 · Build in Canva (status Drafted → Built)
Use the Canva connector. The method that works (learned on Wonder Hour, 3 Oct, final design `DAHW87dwmgg`):
- **Don't generate from scratch.** `create-design` returns pages reversed, drops slides, mixes ~10 fonts and mangles emoji.
- **Clone one good page:** `merge-designs` (create_new_design, a page list like [10,5,5,5…] keeps order and allows duplicates), then rewrite with replace_text / format_text / position.
- The edit API can't set fonts or letter spacing, so **never add new text boxes**; reuse existing ones.
- Cover ghost text with a full-page cream rect (`insert_shape`, then `layer_element back` in a second call).
- Fix orphans and widows by narrowing the text box, not by editing copy.
- **`merge-designs` and committing edits both need her explicit approval.**
- **Editing transactions (fixed 3 Nov after "Editing transaction … not found" errors, 30 Oct–1 Nov):** every edit session starts fresh with `read-design` + `open_transaction: true` (include `thumbnails` for the before state), and uses that exact `transaction_id` straight away. Never reuse an ID from an earlier turn, after a commit/cancel, or after waiting on her or an agent; transactions expire and a stale ID gives "not found". Apply with `finalize: "keep_open"`, show her the after-thumbnail, then a separate call with `commit` (her yes) or `cancel`. If "not found" comes back: open a new transaction and re-apply, don't retry the old ID. Ask her to close the design tab before a build so her edits and ours don't collide.
- If the Canva connector isn't available, fall back to HTML→PNG slides in the post's folder.

## Cost
Canva responses are long, so this is the priciest stage. Build in as few calls as possible, use Sonnet, and don't re-read the design between edits unless something failed.

## Learnings
- 2026-10-03: Wonder Hour build. See the method above.
