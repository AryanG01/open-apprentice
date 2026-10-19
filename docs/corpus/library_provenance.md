# Demo library: provenance

`apps/web/public/samples/library/` holds 100 diagrams written by `scripts/corpus/generate_library.py` (seed 20261019),
authored for this project by its generator: six AI-infrastructure themes (AI factory pipeline, DGX SuperPOD, LLM inference
serving, RAG assistant, Kubernetes GPU cluster, data lakehouse), seeded variation of which boxes appear, their notes and site
names, and deliberately untidy note positions so a taught layout rule has work to do.

- **No external assets:** no images, stencils, data URIs, links or fonts other than draw.io's default (Helvetica); colours are
  plain style values. Nothing is copied from third-party diagrams.
- **Not evaluation data:** the library is kept apart from `tests/fixtures/drawio_corpus/` and `benchmarks/`; no result in
  `docs/evaluation/` uses it. It exists for the product demo (the "teach once, fix 100" wall).
- **Checked:** `tests/unit/test_library.py` (every file listed with its SHA-256 in `index.json`, imports with all notes movable,
  reproducible from the seed) and `tests/integration/test_library_engine.py` (renders in the real draw.io engine; every note is
  single-line and maps to its own box).
- Regenerate: `PYTHONPATH=src:. uv run python scripts/corpus/generate_library.py` (byte-identical output).
