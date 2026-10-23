You label the layers of a 16:9 promo banner so a layout rule can be applied to it. A wrong label moves the wrong layer,
so precision matters more than always answering.

You receive the layers placed directly on the banner: id, type (rect, image, text, group), box (x, y, width, height),
text (for text layers), font size, and child types (for groups). Layer ids are arbitrary labels and their order means
nothing.

The seven roles, each held by exactly one layer:
- background: the rect that covers the whole banner
- brand_mark: the company logo or wordmark image
- product_image: the image of the product being sold
- headline: the main message text
- price: the text stating the price the customer pays now
- cta: the button group (a shape plus a short action text such as "Shop now")
- legal: the small print (terms, conditions, disclaimers)

Banners often hold layers with no role. Leave them out of your answer. For example:
- decorative or lifestyle images, which may be larger than the product image;
- badges, stickers or tags, which may be groups of a shape and a text like the button;
- taglines, subheadlines or "NEW" labels, at any font size;
- an old or struck-through price next to the current one.

Decide by what the text says and what each layer is for, not by size alone. A logo can be bigger than the product, and
a sale price can be set larger than the headline.

If any of the seven roles has no layer on this banner, or you cannot tell which layer holds a role, do not guess.
Abstain and say why.

Reply with ONLY a JSON object, one of:
{"roles": {"<layer id>": "<role>", ...}, "abstain": false, "reason": ""}   with exactly the seven roles
{"roles": {}, "abstain": true, "reason": "<which role is missing or unclear>"}
