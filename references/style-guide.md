# Style guide

## Reference reel, measured

The style comes from a 49.4 s, 1080x1920, 30 fps travel reel, measured with opencv, librosa and macOS Vision OCR. Nothing here was judged by eye.

- Only 2 hard cuts (35.7 s and 37.5 s). Long still holds (motion near 0): 2-6 s, 11-12 s, 21-23.5 s, 28-29 s, 33 s, 45-47 s.
- Opens on a bright flash: brightness 133, down to 67 within about 1.5 s.
- Big centred title, about 68% of the frame width, slightly below centre, 1-11 s. It starts at about 1.15x and settles to 1x in about 0.5 s.
- Small caption, about 13% of the width, 21-23.5 s. Big title on the holds, tiny captions elsewhere.
- Title colour is pure white, RGB (254,255,255), saturation 0.00, wide tracking, no visible gradient or outline. The small caption is pale yellow, RGB (248,236,105).
- One punch-in zoom at 25 s, a bright high-motion burst at 36-43 s, a dark hold at 44-47 s, black by 49 s.
- Audio is 152 bpm (beat 0.395 s). The loudest part is 37-44 s, then near silence at 45-47 s, a last hit at 47.76 s, then black.
- Whole-frame rotation exists only as 3-5 frame whip-spin bursts (up to 12 deg per frame) right before cuts. It is not a slow spin.

## Rules for text

- Flat white, wide letter-spacing, soft drop shadow only.
- One warm accent colour, used on thin rules and nowhere else.
- One serif family for Chinese titles, one light sans for small English tags.
- Vary position, layout and entrance between captions. Do not vary font or effect.
- Do not use calligraphy fonts, gold gradients, thick outlines, orange glows or red seals. They were tried and read as dated next to the reference.

## Checking text

- OCR bounding boxes include shadow, so a measured width reads about 0.05 wider than the glyphs.
- OCR cannot read stylised, rotated or vertical text reliably. For those it proves position and extent, not legibility.
- Do not claim a frame was viewed unless it was. Report measurements instead.

## Timing

- Cut on beats. At 152 bpm one beat is 12 frames at 30 fps.
- Use whip-spin only at cuts, 5 frames before and 5 after.
- Use pulses (channel split plus a brightness lift) on beats in the groove and peak sections only.
- Keep holds still. Motion near zero is part of the look.
