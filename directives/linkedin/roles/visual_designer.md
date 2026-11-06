# Role: Visual Designer (LinkedIn)

**Reads:** `directives/export_linkedin_image.md` in full.
**Writes:** the HTML card(s) + exported PNG(s), linked from the post file's **Visual** section. **Hands to:** QA.

## Per post
- **One card** per post, occasionally two (week 1 used a still + a bio screenshot; week 2 used two generated cards). Default size **1080×1350** (portrait, best feed visibility); use 1080×1080 or 1200×627 only when the content genuinely suits it.
- **Fatz brand colours:** charcoal `#2D3142`, gold `#C9A227`, cream `#FFF8E7`, background `#FAFAFA`.
- **Safe zones:** top 100px, bottom 120px, sides 60–80px minimum. Keep everything critical inside the central 70–80% of the frame.
- **Export:** `npx --yes capture-website-cli` per the directive's exact command, width/height matching the HTML exactly.
- Save to `lead-magnets/linkedin-watch-as-i-grow/visuals/` (or beside the lead magnet itself for a one-off service post).

## Checklist before handing to QA
- [ ] Body background matches card background (no grey border)
- [ ] All text within safe zone margins
- [ ] Nothing important sits in the bottom 120px (LinkedIn's engagement bar overlays there)
- [ ] Font size ≥14px
- [ ] No children's faces, front-on (side angles are fine — the same rule as Instagram)
- [ ] Tested in a browser before export

## Learnings
