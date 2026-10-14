"""Run the label-placement experiment: three systems over frozen episodes, one outcome row per (system, episode).

  apprentice   model proposes candidate rules; batch-first questions; commit on batch agreement or abstain
  agent        the same model, same evidence/teacher/budgets, free-form ask/commit/abstain loop (strong same-model baseline)
  reference    no model: bounded catalogue enumeration + the same loop (ORACLE-ASSISTED, bounds what is achievable)

Modes
  dry    resolve tasks and print the worst-case calls/tokens/dollars; contacts nothing
  mock   apprentice/agent use a scripted stand-in (plumbing only, never model evidence); reference is always local
  live   Nemotron via Nebius Token Factory under SpendGuard (results/redesign/budget.json, spend.jsonl)

Usage: PYTHONPATH=src python scripts/run_label_experiment.py --mode dry --system apprentice,agent --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import pathlib
import time

from open_apprentice.budget import Ledger, Limits
from open_apprentice.concepts.label_agent import MAX_TURNS, run_agent
from open_apprentice.concepts.label_teaching import teach
from open_apprentice.config import load_settings
from open_apprentice.evaluation import spend
from open_apprentice.evaluation.label_episodes import (
    KINDS,
    LabelEpisode,
    agent_visible,
    build_gate_set,
    build_manifest,
    manifest_hash,
)
from open_apprentice.evaluation.label_reference import ReferenceProvider
from open_apprentice.evaluation.label_runner import run_episode, score_and_row
from open_apprentice.providers.base import Provider, estimate_tokens

DEFAULT_MODEL = "nvidia/Nemotron-3-Ultra-550b-a55b"
CONSERVATIVE = spend.CONSERVATIVE_USD_PER_MILLION


def pick(split: str, limit: int | None, kinds: list[str]) -> list[LabelEpisode]:
    eps = [
        e
        for e in (build_gate_set() if split == "gate" else build_manifest(split))
        if e.kind in kinds
    ]
    if limit is None:
        return eps
    out: list[LabelEpisode] = []  # round-robin over kinds so a small sample still covers them
    by = {k: [e for e in eps if e.kind == k] for k in kinds}
    while len(out) < limit and any(by.values()):
        for k in kinds:
            if by[k] and len(out) < limit:
                out.append(by[k].pop(0))
    return out


def worst_case(eps: list[LabelEpisode], systems: list[str], max_tokens: int, floor: int) -> dict:
    out = {}
    for s in systems:
        if s == "reference":
            out[s] = {"calls": 0, "usd": 0.0}
            continue
        calls_per = 3 if s == "apprentice" else MAX_TURNS
        tot_calls, tot_usd = 0, 0.0
        for e in eps:
            view = json.dumps(agent_visible(e), default=str)
            per = estimate_tokens(view) + 2000 + max(max_tokens, floor)
            tot_calls += calls_per
            tot_usd += calls_per * per * CONSERVATIVE / 1e6
        out[s] = {"calls": tot_calls, "usd": round(tot_usd, 2)}
    return out


def make_live_provider(model: str, effort: str | None, floor: int) -> Provider:
    from open_apprentice.providers.factory import make_provider

    st = load_settings()
    raw = dict(st._raw_env)
    raw.setdefault("INPUT_USD_PER_MILLION", "1")
    raw.setdefault("OUTPUT_USD_PER_MILLION", "3")
    raw["INPUT_USD_PER_MILLION"] = raw["INPUT_USD_PER_MILLION"] or "1"
    raw["OUTPUT_USD_PER_MILLION"] = raw["OUTPUT_USD_PER_MILLION"] or "3"
    st = dataclasses.replace(
        st,
        provider_mode="nebius",
        nebius_model=model,
        live_run_max_usd=st.live_run_max_usd or "1",
        nebius_reasoning_effort=effort,
        nebius_completion_cap=floor,
        _raw_env=raw,
    )
    return make_provider(st)


async def run_one(system: str, provider: Provider, ep: LabelEpisode, max_tokens: int) -> dict:
    ledger = Ledger(Limits(tokens=400_000, calls=40))
    view = agent_visible(ep)
    demos = [(d["before"], d["after"]) for d in view["demonstrations"]]
    t0 = time.perf_counter()
    try:
        if system == "agent":
            res = await run_agent(
                provider, ledger, demos, view["batch"], ep.teacher_answer, max_tokens=max_tokens
            )
        else:
            res = await teach(
                provider,
                ledger,
                demos,
                view["batch"],
                ep.teacher_answer,
                max_tokens=max_tokens,
                max_candidates=24 if system == "reference" else 4,
            )
    except Exception as e:
        return {
            "id": ep.id,
            "kind": ep.kind,
            "system": system,
            "outcome": "error",
            "error": f"{type(e).__name__}: {str(e)[:200]}",
        }
    row = score_and_row(ep, res)
    row.update(
        system=system,
        seconds=round(time.perf_counter() - t0, 1),
        tokens=ledger.consumed_tokens,
        calls=ledger.consumed_calls,
    )
    return row


async def main(a: argparse.Namespace) -> None:
    systems = a.system.split(",")
    kinds = a.kinds.split(",") if a.kinds else list(KINDS)
    eps = pick(a.split, a.limit, kinds)
    if a.only:
        eps = [e for e in eps if any(t in e.id for t in a.only.split(","))]
    run_id = a.run_id or time.strftime("%Y%m%d-%H%M%S")
    wc = worst_case(eps, systems, a.max_tokens, a.completion_floor)
    budget = spend.load_budget()
    print(
        f"run {run_id}: {len(eps)} episodes x {systems}  split={a.split}  manifest={manifest_hash(build_gate_set() if a.split == 'gate' else build_manifest(a.split))[:12]}"
    )
    print(f"worst case (conservative $4/M, retries not included): {wc}")
    print(
        f"shared budget: spent ${spend.spent_so_far():.2f}, spendable ${spend.spendable(budget):.2f} (authorized {budget['authorized_total_usd']}, funded {budget['funded_usd']}, reserve {budget['reserve_usd']})"
    )
    if a.mode == "dry":
        return
    out = pathlib.Path("results/redesign") / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(
        json.dumps(
            {
                "run": run_id,
                "mode": a.mode,
                "systems": systems,
                "split": a.split,
                "episodes": [e.id for e in eps],
                "model": a.model,
                "effort": a.effort,
                "max_tokens": a.max_tokens,
                "run_cap_usd": a.cap_usd,
            },
            indent=1,
        )
    )
    rows = []
    streak = 0
    provider: Provider | None = None
    guard = None
    try:
        if a.mode == "live" and any(s != "reference" for s in systems):
            if a.cap_usd <= 0:
                raise SystemExit("--cap-usd is required for live runs")
            guard = spend.SpendGuard(
                make_live_provider(a.model, a.effort, a.completion_floor),
                run_id=run_id,
                run_cap_usd=a.cap_usd,
                merge_system=True,
            )
            provider = guard
        for ep in eps:
            for s in systems:
                if s == "reference":
                    prov: Provider = ReferenceProvider()
                elif provider is None:
                    raise SystemExit(
                        "mock mode runs only the reference system; use --system reference or --mode live"
                    )
                else:
                    prov = provider
                before = guard.run_usd if guard else 0.0
                row = await run_one(s, prov, ep, a.max_tokens)
                row["run_usd_after"] = round(guard.run_usd, 4) if guard else 0.0
                row["usd"] = (
                    round((guard.run_usd - before), 4) if guard and s != "reference" else 0.0
                )
                row["label"] = prov.label
                rows.append(row)
                with open(out / "outcomes.jsonl", "a") as f:
                    f.write(json.dumps(row, default=str) + "\n")
                print(
                    f"{ep.id:<30} {s:<10} {row['outcome']:<20} q={row.get('questions','-')} ${row['usd']:.3f}  run=${row['run_usd_after']:.3f}"
                )
                streak = streak + 1 if row["outcome"] == "error" else 0
                if streak >= 2:
                    print("STOPPED: two consecutive provider errors; nothing further was spent")
                    raise SystemExit(3)
                if guard and guard.stopped_reason:
                    print(f"STOPPED: {guard.stopped_reason}")
                    raise SystemExit(2)
    finally:
        if provider is not None:
            await provider.aclose()
        summ: dict = {}
        for r in rows:
            k = (r["system"], r["kind"])
            summ.setdefault(f"{k[0]}/{k[1]}", {}).setdefault(r["outcome"], 0)
            summ[f"{k[0]}/{k[1]}"][r["outcome"]] += 1
        (out / "summary.json").write_text(
            json.dumps(
                {"counts": summ, "run_usd": round(guard.run_usd, 4) if guard else 0.0}, indent=1
            )
        )
        print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["dry", "mock", "live"], default="dry")
    p.add_argument("--system", default="apprentice,agent,reference")
    p.add_argument("--split", default="development")
    p.add_argument(
        "--only", default="", help="comma-separated substrings; keep episodes whose id contains one"
    )
    p.add_argument("--limit", type=int)
    p.add_argument("--kinds")
    p.add_argument("--cap-usd", type=float, default=0.0)
    p.add_argument("--run-id")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--effort", default="low")
    p.add_argument("--max-tokens", type=int, default=6000)
    p.add_argument("--completion-floor", type=int, default=32000)
    asyncio.run(main(p.parse_args()))
