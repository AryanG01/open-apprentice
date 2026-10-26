You see a rough hand-drawn wireframe of a 16:9 promo banner (boxes, scribbles standing for text, crossed boxes or sketches for
pictures, labels). The user message gives the canvas size. List the layers the designer intended, each with exactly one of
these roles: brand_mark, product_image, headline, price, cta, legal.

For every layer give:
- "box": [x_min, y_min, x_max, y_max] on a 0 to 1000 grid of the image (0,0 is the top-left corner, 1000,1000 the
  bottom-right). Boxes may be loose; draw them around the whole intended area (all the lines of a text block, the whole
  crossed box).
- "text": only if clearly legible handwriting says words, exactly as written; otherwise an empty string. Scribbles are not words.
- "font_px": a rough estimate of the text size on a 1280 x 720 canvas (0 for the two picture roles).
- "bold": true only when the lettering looks heavy.
- "color": #rrggbb only if something in the sketch indicates it (a coloured pen, a written colour name); otherwise an empty string.
- "fill": empty string.

Role cues:
- a small box in a top corner = brand_mark
- the largest roughly square or crossed box = product_image
- the biggest block of text lines = headline
- a short line with digits or a currency sign = price
- a rounded box with a short word = cta
- the smallest text lines near the bottom = legal

Each role at most once. If a role is not in the sketch, leave it out. Never invent.

Also give "language": the two-letter code of the handwriting, or "en" when there is none.

Reply with ONLY a JSON object: {"language": "en", "layers": [{"role": "...", "box": [..], "text": "", "font_px": 40,
"bold": false, "color": "", "fill": ""}, ...]}.
