# Open Apprentice Gym: calibrated asking as a NeMo Gym environment

A [NeMo Gym](https://docs.nvidia.com/nemo/gym) resources server (`resources_servers/oa_calibrated_asking`). An agent sees ONE demonstration of a hidden
layout rule (badge placement or row spacing) and may call:

- `ask(card_widths)`: the teacher shows the true outcome on a new input (at most 3; each costs),
- `commit(rule)`: the final rule, as text in a closed grammar (parsed and evaluated exactly; no `eval`),
- `abstain(reason)`.

`/verify` scores the episode by exact rational evaluation of the committed rule against held-out scenes, **with no LLM judge**, and returns
**separate reward components** (`BaseMultiRewardVerifyResponse`): `correct`, `held_out`, `asking`, `not_confidently_wrong`, `economy`. The scalar
`reward` is the single component `correct`; it is not a sum or a blend, and the components are never combined into a "score".

*Calibrated asking*: `asking` is 1 iff the agent asked when the demonstration was genuinely ambiguous, or did not ask when it was not.
Ambiguity is computed by the environment (the reference teaching loop needed at least one question), never by the agent, so it is relative to the
declared rule grammar. 15 of the 24 development demonstrations are ambiguous.

The environment logic is plain Python in the main project (`../src/open_apprentice/evaluation/asking_env.py`, tests in `../tests/unit`); this folder is the
thin Gym wrapper. Scripted baseline results (no model) are in `../results/asking_baselines/` and `../docs/decisions.md` #53.

## Setup (a separate Python: nemo-gym 0.6.0 needs >= 3.13.14)

The main project stays on Python 3.12. Python 3.14.8 does NOT work with the Gym CLI (an argparse `LazyCompletionHelp` incompatibility inside nemo-gym's Hydra
parser); use 3.13.x:

```bash
# a self-contained CPython 3.13.16 (python-build-standalone, ~25 MB), kept inside gym/ and git-ignored
mkdir -p .python && cd .python
curl -sL -o py.tar.gz "https://github.com/astral-sh/python-build-standalone/releases/download/20261009/cpython-3.13.16%2B20261009-aarch64-apple-darwin-install_only.tar.gz"
tar -xzf py.tar.gz && cd ..                      # pick the asset for your platform
uv sync --python .python/python/bin/python3
PYTHONPATH=../src .venv/bin/python resources_servers/oa_calibrated_asking/create_dataset.py   # writes data/*.jsonl
PYTHONPATH=../src .venv/bin/python -m pytest resources_servers/oa_calibrated_asking/tests -q
.venv/bin/gym list resources-servers --search-dir .   # oa_calibrated_asking appears next to NVIDIA's environments
```

The Open Apprentice package is imported from `../src` (see `app.py`), not installed: the main project's `requires-python` (<3.14) would exclude
the interpreter nemo-gym needs, and the evaluation code only needs `z3-solver==4.13.4.0`, `pydantic`, `httpx` and `pyyaml`.

## Notes
- `gym env init` and `gym list` crash on Python 3.14.8 (see above); `REVERIFY_MODE` is `UNSUPPORTED` because the episode state lives in server memory.
- The `abstention` environment that ships in nemo-gym 0.6.0 rewards saying "I don't know" on LLM-judged factual QA. This one differs by rewarding a targeted
  question to a teacher only when the demonstration is genuinely ambiguous, by computing ambiguity in the environment, and by verifying with exact evaluation.
  Only the packages shipped in 0.6.0 were checked.
