# Third-party notices

Open Apprentice's own code is MIT licensed (see `LICENSE`). This file tracks third-party
dependencies, assets, and research artifacts that carry their own license or usage terms.
Update it whenever a new runtime dependency, asset, or borrowed fixture is added.

## Runtime dependencies

Exact licenses for pinned Python and Node dependencies are resolvable from `uv.lock` and
`package-lock.json`. No dependency's source code is vendored into this repository; all are
installed from their official package registries (PyPI, npm) under their declared licenses.

Notable dependencies and their roles:

| Package | Role | License (verify against installed version) |
| --- | --- | --- |
| Konva | first graphics backend (§6.1) | MIT |
| Fabric.js | second graphics backend (§6.1, §6.7) | MIT |
| Playwright | browser automation for the engine service | Apache-2.0 |
| z3-solver | bounded witness search (§8.9) | MIT |
| FastAPI | HTTP API | MIT |
| SQLAlchemy | persistence | MIT |

## Research artifacts referenced but not vendored

Per §2 and §0.6/§21.12, the following public research artifacts informed design decisions. None
of their code is copied into this repository without a separate, explicit license check recorded
here before any such copy is made:

- GEPA (https://github.com/gepa-ai/gepa) — inspiration for reflective repair search (§11.2). Not
  vendored; no code copied.
- Socrates (https://github.com/celestebarnaby/socrates) — inspiration for disambiguating queries
  (§2.6, §8.6). License not verified as of this writing; reimplemented independently, not copied.
- ContractSkill (https://github.com/underfitting-lu/contractskill) — inspiration for the
  structured-procedure baseline (§21.11). Not vendored; no code copied.
- Vector-Bench (https://github.com/yug-space/vector-edit-gym) — external evaluation harness for
  the v1.3 SVG lane (§21.12). If used, only a frozen evaluator commit is referenced; its dataset's
  20 scenic illustrations are explicitly excluded from this project and from any public demo per
  the dataset's own NOTICE.md (see docs/decisions.md for the enforcement mechanism).

## Third-party design assets in the public demo

Only owner-authored or independently provenance-verified assets are bundled or shown in the public
demo or submission video. Each asset's origin is recorded in `docs/decisions.md` before inclusion.
