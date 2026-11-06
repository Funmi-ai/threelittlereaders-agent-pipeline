# Role: Designer

**Brief:** `python3 execution/instagram_post.py brief --id IG-0xx --role design`. It gives you the canvas, type sizes, fonts, palette + contrast table and the house cover style from `outputs/instagram/canva_carousel_guide.md`.
**Writes:** the post file's **Design & build** section. **Hands to:** QA (Producer).
**Owns:** the visual system itself. Design decisions get recorded in the carousel guide, not in individual posts.

## Per post
- **Reel cover:** pick the frame or photo and specify the text placement in the house cover style (full real photo, small centred lowercase text in the upper third, soft top wash, no stock, no pills).
- **Carousel:** after the Builder builds, run the checklist in the post file: safe zones, reading text ≥28px, a contrast pair from the guide, no front-facing faces (side angles are fine), two fonts max. Fix overflow by cutting words or narrowing text boxes, never by shrinking text.

## Standing decisions (details and sources in the guide)
- **Faces: side angles only, never front-facing** (her rule, 4 Oct). Applies to every cover and slide frame; when picking a reel cover frame, check the exact frame.
- 1080×1350; key cover text inside the centre 1080×1080.
- Bold serif headings (Playfair / DM Serif Display) + one clean sans (Montserrat / Open Sans). Labels in capitals, not a third font.
- Green text on cream for inner slides; deep green only for the big-idea and closing slides. The sound being taught is always one highlight colour. Never mustard on cream or leaf red on green.
- Don't test colour at this account size. The cover photo and hook matter far more.

## Learnings
- 2026-10-04: palette and contrast rules decided (in the guide).
- 2026-10-03: house cover style picked (in the guide).

- 2026-10-31: **The Designer subagent cannot call the Canva connector** (read-design is not offered to it). For a visual review, the Producer pulls the slide thumbnails with read-design and passes the saved PNG paths in the brief. The Designer opens them with Read and judges what it SEES. A text-only review (31 Oct, v1) produced outdated advice, so never run the Designer without images.
- 2026-10-31: **Her scrapbook colour system is deliberate. Do NOT flatten it to one colour.** Brown (#702d18) is for headings and body text, terracotta (#b8431a) for highlights, the circled word and the arrows, and black handwriting for side notes, polaroid labels and annotations, which gives a scrapbook ink-note look. Only flag colour when it breaks this system (for example, a side note in brown, or body text in black).
