# Held-out run: protocol, frozen 29 Oct 2026 before any image was opened or any model call

**Code frozen at** commit `64df984` (code unchanged since `337ddcb`; later commits are docs). Models: `nvidia/Nemotron-3.5-Super-VL` (reading) and `nvidia/nemotron-3-super-120b-a12b` (question wording). Vision prompt hash as in `fresh_synthetic_protocol.md`.

**What was received.** `Archive.zip` from the owner: 19 WhatsApp-compressed JPEG files (not originals), 17 unique by SHA-256 (two pairs are byte-identical copies), with no
prompts and no `expected.json`, although 8 banners were requested. Consequences, stated now: (1) the "first output, no retries" rule cannot be verified, the
provenance is the owner's word; (2) because there are more images than cases, **no image is selected out: every unique image is run, once**; (3) the images are
JPEG-compressed, which is easier on nobody but is what real-world uploads often are; (4) the expected text of each image was written by the assistant by reading the image
**after** this protocol was committed (the assistant is also the author of the product: a bias, so exports are also scored by a fresh-context reviewer).

**Procedure (fixed).** Each unique image is uploaded once through the real Adapt screen on a local build of the frozen code with live models.
The raw reading is saved before the expected text is applied. A scripted operator then: replaces a text field that differs from the expected text (counted); does
**not** edit any box; picks split if both layouts fit, else shrink, else neither; on the busy-background screen, takes "Choose another banner" (counted as
a correct refusal, nothing was sent to the model). Anything the app blocks is reported as blocked. No retry of any step. Cost cap for the run: $0.30.

**Scoring (fixed).** Per image: raw roles and text exact; corrections; outcome (clean card / flawed card / refused before the model / blocked / no card);
for built cards a fresh-context reviewer scores the exported card against the checklist in `docs/plan/strict_rubric.md` at phone size (every approved word present and legible; product whole
and undistorted; no fragment of another element; logo intact; nothing outside the safe area; no accidental overlap; spacing balanced). Reported as: clean / in-envelope inputs, and correct
refusals / out-of-envelope inputs. A fix made after seeing these results is a development change, and this set is then spent.

## Amendment, 29 Oct 2026, after viewing the images and before any model call
- The assistant looked at all 17 images (contact sheets) to write `expected.json` (text read by eye; the brief's wording was used for each case). Mapping: H1 tall bottle x3 (HO_11-13), H2 tall tower x1 (HO_01), H3 soft gradient x1 (HO_14),
  H4 photograph x4 (HO_05, 15, 16, 17), H5 long English headline x3 (HO_08-10), H6 long German headline x3 (HO_02-04), H8 stacked centred x2 (HO_06-07). **H7 (unusual layout) was not delivered.**
  Several cases arrived as 2 to 4 variants, so the owner generated more than once: the "first output" rule was not kept, and no variant is dropped here.
- In-envelope (flat background): 12 images (H1, H2, H5, H6, H8). Out-of-envelope: 5 images (H3, H4); the flat detector decides, and a soft gradient may pass it: that is recorded as it happens.
- The app's per-address limit is 10 vision reads an hour, so the 17 images run in two batches with the local server restarted between them (local evaluation only; the cost cap is $0.30 for the whole run).
