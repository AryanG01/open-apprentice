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
