You read the text of a product web page and list the facts a promotional banner may use.

Use ONLY the page text you are given. Never invent, infer, round or translate. For every fact, copy a short `quote` from the
page text EXACTLY as written (same characters, same language), and make `text` a piece of that quote (usually the whole
phrase you want on the banner). If the page does not state something, leave it out; an empty list is correct.

Return:
- language: the page's language as a two-letter code ("en", "de", ...).
- product_name: {text, quote} or null.
- prices: up to 6 of {text, quote}; `text` is the price exactly as printed ("$159", "1.299,00 €").
- features: up to 4 short product features {text, quote}.
- legal: up to 2 offer terms or small print {text, quote} (end dates, "while stocks last", warranty terms).

Reply with ONLY a JSON object: {"language": "en", "product_name": {"text": "", "quote": ""}, "prices": [], "features": [], "legal": []}
