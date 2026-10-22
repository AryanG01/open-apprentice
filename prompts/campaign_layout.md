You learn a layout rule for adapting a 16:9 promo banner into a 1080x1920 (9:16) story card from ONE before/after example.

You receive, per role, the node's box before and after (x, y, w, h in its parent's frame), its type, and its font size / corner
radius before and after. Roles: background, brand_mark, product_image, headline, price, cta, legal, and the CTA's children
`cta/shape` (the button plate) and `cta/text` (its label).

Reply with ONLY a JSON object: {"candidates": [{"rule": [...], "summary": "..."}]}, at most 3 candidates.

A rule is a list of statements in this restricted language:
- {"op":"for_each","over":{"ref":"objects"},"var":"o","body":[...]}
- {"op":"if","cond":<expr>,"then":[...],"else":[...]}
- {"op":"emit_target","kind":"place","target":{"ref":"locals.o"},"x":<n>,"y":<n>,"w":<n>,"h":<n>,"z":<int>} (z optional)
- {"op":"emit_target","kind":"fit_image","target":{"ref":"locals.o"},"x":<n>,"y":<n>,"w":<n>,"h":<n>} (images: fit inside the box, never cropped)
- {"op":"emit_target","kind":"style","target":{"ref":"locals.o"},"fontSize":<n>} or "cornerRadius":<n>
Expressions: ints, {"rat":"a/b"}, {"ref":"canvas.w"}, {"ref":"canvas.h"}, {"op":"get","args":[{"ref":"locals.o"},"role"]} and
{"op":"<add|sub|mul|div|min|max|eq|ne|lt|le|gt|ge|and|or|not>","args":[...]}. No floats. The canvas is the 1080x1920 card.

Copy, links, colours and images are never changed: no other emit kinds or fields exist. Overflow handling is built in and is
not part of your rule. The rule must reproduce the example exactly.
