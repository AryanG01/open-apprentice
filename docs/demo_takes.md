# Demo video takes (2026-10-19/20)

Every recording below was made against the deployed site, with the live model (Nemotron-3-Super on Nebius Token Factory,
product policy `product-1`), by `video/capture/capture.mjs`. A scripted person answers each question by comparing the
rendered outcomes with the intended placement: every note left-aligned with its box, 8 units below it. The published video
uses the last take. The earlier takes are listed with what went wrong.

| Take | Outcome | Why it was not used |
|---|---|---|
| 1 (10-18) | live session failed after about 11 min: `provider: truncation` (Ultra, before product-1) | failure; it led to product-1 and the model check |
| 2–4 (10-19) | committed; the wall published 100/100 | before the plain-language redesign; the option cards were mis-sized (CSS) |
| 5 (10-19) | committed, but the wall published **90, with 10 blocked** | the scripted person picked an option by its wording ("fixed gap of 64"), not by its picture. On taller boxes that rule would overlap, and the layout check blocked those 10 files instead of publishing them |
| 6–7 (10-20) | stopped before the finale (Cloud Run instance limit; the big map rendered behind the wall's thumbnails) | infrastructure; fixed with max instances 6, lighter polling and an earlier upload |
| 8 (10-20) | committed after 1 question; 102/102 published; the 217-object map published with all three checks | **used** |

Live spend for all takes: well under $1 on the durable ledger (`/health/ready`).
