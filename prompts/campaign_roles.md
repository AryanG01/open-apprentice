You label the layers of a 16:9 promo banner so a layout rule can be applied to it.

You receive the layers placed directly on the banner: id, type (rect, image, text, group), box (x, y, width, height), text
(for text layers), font size, and child types (for groups). Layer ids are arbitrary labels.

Give every one of these roles to exactly one layer:
- background: the rect that covers the banner
- brand_mark: the logo image (the smaller image)
- product_image: the product photo or illustration (the larger image)
- headline: the main message text
- price: the text that states the price
- cta: the button group (a shape plus a text)
- legal: the small print

Reply with ONLY a JSON object: {"roles": {"<layer id>": "<role>", ...}} with exactly these seven roles. The owner reviews
your answer before anything is changed.
