"""Local app server for the fresh-set evaluation: the real app, plus a log of every model call (role, raw reply text, usage; never
images) in a JSONL file. Modes:
  record          vision and text calls go live and are logged
  replay-vision   the vision model answers from the logged replies (no second paid read of the same image); the text model is live
Environment for the live run comes from .env as usual (the key is never printed). Usage:
  uv run python scripts/eval_server.py --port 8780 --mode record --calls out/calls.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
from contextlib import asynccontextmanager

import uvicorn


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8780)
    ap.add_argument("--mode", choices=["record", "replay-vision"], default="record")
    ap.add_argument("--calls", required=True)
    ap.add_argument("--max-usd", default="1.00")
    ap.add_argument(
        "--replay-skip",
        type=int,
        default=0,
        help="drop this many logged vision replies first (to replay one later image)",
    )
    args = ap.parse_args()

    os.environ["DEMO_MODEL_ENABLED"] = "1"
    os.environ["DEMO_MODEL_MAX_USD"] = (
        args.max_usd
    )  # the incremental cap for this run, far below the owner's $5 total
    os.environ.setdefault("SESSION_SECRET", "local-eval-" + os.urandom(8).hex())  # local only
    os.environ.setdefault("NEBIUS_VISION_MODEL", "nvidia/Nemotron-3.5-Super-VL")
    os.environ.setdefault("NEBIUS_MODEL", "nvidia/nemotron-3-super-120b-a12b")
    os.environ["PAGE_MODE"] = "mock"
    os.environ.setdefault(
        "VISION_INPUT_USD_PER_MILLION", "0.30"
    )  # Token Factory list price of the VL model
    os.environ.setdefault("VISION_OUTPUT_USD_PER_MILLION", "0.90")

    from open_apprentice.providers import nebius as nb  # noqa: E402
    from open_apprentice.providers.mock import MockProvider  # noqa: E402

    _orig = nb.NebiusProvider._call

    async def _logged(self, messages, *, max_tokens, ctx):
        comp = await _orig(self, messages, max_tokens=max_tokens, ctx=ctx)
        with open(args.calls, "a") as f:
            f.write(
                json.dumps(
                    {
                        "role": ctx.role,
                        "model": comp.model_id,
                        "request_id": comp.request_id,
                        "prompt_tokens": comp.prompt_tokens,
                        "completion_tokens": comp.completion_tokens,
                        "usd": comp.usd,
                        "latency_ms": comp.latency_ms,
                        "finish_reason": comp.finish_reason,
                        "text": comp.text,
                    }
                )
                + "\n"
            )
        return comp

    nb.NebiusProvider._call = _logged

    from open_apprentice.api.app import app  # noqa: E402

    if args.mode == "replay-vision":
        saved = [json.loads(line) for line in open(args.calls) if line.strip()]
        replies = [c["text"] for c in saved if c["role"] == "campaign_vision"][args.replay_skip :]
        orig_lifespan = app.router.lifespan_context

        @asynccontextmanager
        async def lifespan(a):
            async with orig_lifespan(a):
                a.state.vision_provider = MockProvider({"campaign_vision": replies})
                yield

        app.router.lifespan_context = lifespan

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":  # the engine is a spawned child that re-imports this file
    main()
