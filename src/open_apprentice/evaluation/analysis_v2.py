"""Plan 5 analysis (spec 7). The unit is the episode: per-episode success rate over repeats, paired differences between
two systems, a paired bootstrap over episodes (all repeats kept) and an exact two-sided sign test with ties reported.
Intervals describe this task collection only. Offline rows are never presented as model results."""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from math import comb
from pathlib import Path
from statistics import mean
from typing import Iterable, Optional, Union

SUCCESS = ("correct_complete", "appropriate_refusal")
LEARNING = {"catalogue", "beyond"}
Strata = Optional[Union[str, set[str]]]


def _in(row: dict, stratum: Strata) -> bool:
    if stratum is None:
        return True
    return row["stratum"] in ({stratum} if isinstance(stratum, str) else stratum)


def episode_rates(rows: Iterable[dict], system: str, stratum: Strata = None) -> dict[str, float]:
    per: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        if r["method"] == system and _in(r, stratum):
            per[r["episode"]].append(int(r["terminal_outcome"] in SUCCESS))
    return {e: mean(v) for e, v in sorted(per.items())}


def sign_test(pos: int, neg: int) -> dict:
    """Exact two-sided binomial test (p = 1/2) on the non-tied pairs."""
    n = pos + neg
    if n == 0:
        return {"p_exact": 1.0}
    tail = sum(comb(n, k) for k in range(min(pos, neg) + 1)) / 2**n
    return {"p_exact": min(1.0, 2 * tail)}


def paired(
    rows: list[dict], a: str, b: str, stratum: Strata = None, draws: int = 10_000, seed: int = 0
) -> dict:
    ra, rb = episode_rates(rows, a, stratum), episode_rates(rows, b, stratum)
    eps = sorted(set(ra) & set(rb))
    d = [ra[e] - rb[e] for e in eps]
    pos, neg = sum(x > 0 for x in d), sum(x < 0 for x in d)
    out: dict = {
        "a": a,
        "b": b,
        "n_episodes": len(eps),
        "mean_diff": mean(d) if d else None,
        "ci95": None,
        "sign": {"pos": pos, "neg": neg, "ties": len(d) - pos - neg} | sign_test(pos, neg),
    }
    if len(d) >= 2:  # the same episode resampling as metrics.paired_cluster_bootstrap
        rng = random.Random(seed)
        boots = sorted(mean(rng.choices(d, k=len(d))) for _ in range(draws))
        out["ci95"] = [boots[int(0.025 * draws)], boots[int(0.975 * draws) - 1]]
    return out


def _fmt(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x:+.3f}"


def _paired_line(p: dict) -> str:
    ci = "n/a" if p["ci95"] is None else f"[{p['ci95'][0]:+.3f}, {p['ci95'][1]:+.3f}]"
    s = p["sign"]
    return (
        f"{p['a']} − {p['b']}: mean episode difference {_fmt(p['mean_diff'])}, 95% bootstrap {ci}, "
        f"{p['n_episodes']} episodes; sign test +{s['pos']} / −{s['neg']} / ties {s['ties']}, "
        f"p = {s['p_exact']:.4f}"
    )


def _table(rows: list[dict], systems: list[str], key: str) -> list[str]:
    groups = sorted({r[key] for r in rows})
    lines = [f"| {key} | " + " | ".join(systems) + " |", "|---|" + "---|" * len(systems)]
    for g in groups:
        cells = []
        for s in systems:
            sel = [r for r in rows if r["method"] == s and r[key] == g]
            ok = sum(r["terminal_outcome"] in SUCCESS for r in sel)
            cells.append(f"{ok}/{len(sel)}" if sel else "–")
        lines.append(f"| {g} | " + " | ".join(cells) + " |")
    return lines


def report(run_dir: Path) -> str:
    run_dir = Path(run_dir)
    rows = [json.loads(x) for x in (run_dir / "rows.jsonl").read_text().splitlines() if x.strip()]
    manifest = json.loads((run_dir / "manifest.json").read_text())
    systems = sorted({r["method"] for r in rows})
    offline = manifest.get("mode") != "live" or any(r["origin"] != "live" for r in rows)
    out = [f"# Evaluation report — {manifest.get('run_id', run_dir.name)}", ""]
    if offline:
        out += [
            "**Offline dry run — not a model result.** Rows are `origin=mock` with a fixture candidate source "
            "(`model=Fixture`): they check the pipeline, the scoring and the boundary, and say nothing about any model.",
            "",
        ]
    out += [
        f"Split `{manifest.get('split')}`, mode `{manifest.get('mode')}`, systems {', '.join(systems)}.",
        "",
    ]
    refused = manifest.get("adapter_refused") or {}
    if refused:
        out += ["## Not run: refused by the draw.io adapter", ""]
        out += [f"- `{k}`: {v}" for k, v in sorted(refused.items())]
        out += [
            "",
            "The product's adapter refuses these files, so no system was run on them; the refusal is the same for every "
            "system and is reported rather than worked around.",
            "",
        ]
    stops = sum(1 for r in rows if r.get("failure") == "budget_stop")
    out += [
        f"Coverage: runs with an outcome: {len(rows) - stops} of {len(rows)} ({stops} stopped by the dollar cap).",
        "",
    ]
    cost_rows = rows  # cost and diagnostics include stopped runs; outcomes do not
    rows = [r for r in rows if r.get("failure") != "budget_stop"]

    blocking = Counter(b for r in rows for b in r.get("release_blocking", []))
    mislabelled = sum(
        1
        for r in rows
        if r["origin"] == "live" and (manifest.get("mode") != "live" or r.get("model") == "Fixture")
    )
    out += [
        "## Release-blocking checks",
        "",
        f"- boundary violations: {blocking['boundary_violation']}",
        f"- accepted preservation violations: {blocking['accepted_preservation_violation']}",
        f"- unexplained retention regressions: {blocking['unexplained_retention_regression']}",
        f"- rows labelled live in a mock run: {mislabelled}",
        "",
        "## Primary endpoints",
        "",
    ]
    pairs = [("A", "B")] if {"A", "B"} <= set(systems) else []
    pairs += [("A", s) for s in systems if s not in ("A", "B") and "A" in systems]
    seq = [r for r in rows if r["stratum"] == "sequential"]
    for name, strata in (
        ("learning success", LEARNING),
        ("correction success (end to end)", "sequential"),
    ):
        out.append(f"**{name}**" + (" (fixture, not a model result)" if offline else ""))
        out.append("")
        for s in systems:
            sel = [r for r in rows if r["method"] == s and _in(r, strata)]
            ok = sum(r["terminal_outcome"] in SUCCESS for r in sel)
            out.append(f"- {s}: {ok}/{len(sel)} runs")
        out += [f"- {_paired_line(paired(rows, a, b, strata))}" for a, b in pairs]
        out.append("")
    if any(r.get("correction_policy") == "A" for r in seq):
        out += [
            "Note: system B's correction cycle runs A's correction policy (the shared correction executor and scope "
            "proposer), so the correction endpoint for A − B reflects acquisition only; it is not a comparison of "
            "correction policies.",
            "",
        ]
    out.append("Correction success given acquisition (denominator = runs that acquired the rule):")
    for s in systems:
        acq = [r for r in seq if r["method"] == s and (r.get("correction") or {}).get("acquired")]
        ok = sum(bool(r["correction"].get("success")) for r in acq)
        out.append(f"- {s}: {ok}/{len(acq)}")
    out += ["", "## Per stratum", "", *_table(rows, systems, "stratum"), ""]
    out += ["## Per behaviour spec", "", *_table(rows, systems, "spec_kind"), ""]
    out += ["## Terminal outcomes", ""]
    for s in systems:
        c = Counter(r["terminal_outcome"] for r in rows if r["method"] == s)
        out.append(f"- {s}: " + ", ".join(f"{k} {c[k]}" for k in sorted(c)))
    out += ["", "## Refusals by kind", ""]
    for s in systems:
        k = Counter(
            r.get("refusal_kind") or "unknown"
            for r in rows
            if r["method"] == s and r["terminal_outcome"] == "appropriate_refusal"
        )
        out.append(f"- {s}: " + (", ".join(f"{x} {k[x]}" for x in sorted(k)) or "none"))
    out += ["", "## Diagnostics (sums)", ""]
    for s in systems:
        d: Counter = Counter()
        for r in rows:
            if r["method"] == s:
                d.update({k: int(v) for k, v in (r.get("diagnostics") or {}).items()})
        out.append(f"- {s}: " + ", ".join(f"{k} {d[k]}" for k in sorted(d)))
    seq_rows = [r for r in cost_rows if r["stratum"] == "sequential"]
    out += ["", "## Correction effort (sequential episodes, mean per run)", ""]
    for s in systems:
        sel = [r for r in seq_rows if r["method"] == s]
        if not sel:
            continue
        calls = mean((r.get("diagnostics") or {}).get("correction_proposer_calls", 0) for r in sel)
        turns = mean((r.get("diagnostics") or {}).get("correction_agent_turns", 0) for r in sel)
        out.append(f"- {s}: proposer calls {calls:.1f}, agent turns {turns:.1f}")
    out += [
        "",
        "B's correction cycle may use more provider calls than A's: every B decision is itself a model call, and B gets the",
        "spec's 4 correction attempts plus whatever its learning cycle left unused (never more than 12 in all). A's policy runs",
        "at most a scope round and one revision round. Read the correction comparison with that difference in mind.",
    ]
    out += ["", "## Cost per episode (every run, stopped ones included)", ""]
    for s in systems:
        sel = [r for r in cost_rows if r["method"] == s]
        usd = [r["usd"] for r in sel if r.get("usd") is not None]
        out.append(
            f"- {s}: mean ${mean(usd) if usd else 0:.4f}, mean tokens {mean(r['tokens'] for r in sel):.0f}, "
            f"mean wall {mean(r['wall_s'] for r in sel):.1f} s"
        )
    out += ["", "## Repeat-to-repeat variation", ""]
    for s in systems:
        reps = sorted({r["rep"] for r in rows if r["method"] == s})
        rates = []
        for k in reps:
            sel = [r for r in rows if r["method"] == s and r["rep"] == k]
            rates.append(f"r{k} {sum(r['terminal_outcome'] in SUCCESS for r in sel)}/{len(sel)}")
        out.append(f"- {s}: " + ", ".join(rates))
    out += ["", "Intervals describe this task collection only.", ""]
    return "\n".join(out)


COMPLETION_ASSUMED = (
    2000  # tokens per live attempt: an ASSUMPTION until the calibration run measures it
)
PROMPTS = Path(__file__).resolve().parents[3] / "prompts"


def token_estimate(run_dir: Path) -> dict:
    """Per-episode tokens for pricing, from a dry run's kept outcomes. Prompt sizes are real (B: the mock provider's
    estimate of each prompt it received; A: the system prompt plus the episode's demonstrations as sent); completion
    tokens are assumed (COMPLETION_ASSUMED per attempt) and are what the calibration run is for."""
    from open_apprentice.providers.base import estimate_tokens

    run_dir = Path(run_dir)
    sys_prompt = {
        "learn": estimate_tokens((PROMPTS / "hypotheses_labels.md").read_text()),
        "correct": estimate_tokens((PROMPTS / "correction_scope.md").read_text()),
    }
    rows = [json.loads(x) for x in (run_dir / "rows.jsonl").read_text().splitlines() if x.strip()]
    per: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for r in rows:
        f = run_dir / "episodes" / f"{r['episode']}-{r['method']}-r{r['rep']}" / "outcome.json"
        evs = json.loads(f.read_text()).get("events", []) if f.exists() else []
        evidence = {
            log: estimate_tokens(
                json.dumps(
                    [
                        e["payload"]
                        for e in evs
                        if e.get("log", "learn") == log
                        and (
                            e["type"] in ("DemonstrationRecorded", "CorrectionStarted")
                            or (
                                e["type"] == "SceneRegistered"
                                and e["payload"].get("role") == "demo"
                            )
                        )
                    ]
                )
            )
            for log in ("learn", "correct")
        }
        attempts = tokens = 0
        for e in evs:
            if e["type"] == "AgentTurn":
                tokens += int((e["payload"].get("usage") or {}).get("prompt_tokens", 0))
                tokens += COMPLETION_ASSUMED
            elif e["type"] == "ActionIssued" and e["payload"].get("kind") == "AgentTurn":
                attempts += 1
            elif e["type"] == "ActionIssued" and e["payload"].get("kind") == "RequestModelProposal":
                log = e.get("log", "learn")
                attempts += 1
                tokens += sys_prompt[log] + evidence[log] + COMPLETION_ASSUMED
        per[r["method"]].append((attempts, tokens))
    return {
        "per_system": {
            s: {
                "episodes": len(v),
                "attempts_mean": mean(a for a, _ in v),
                "tokens_per_episode": round(mean(t for _, t in v)),
                "tokens_per_episode_max": max(t for _, t in v),
            }
            for s, v in sorted(per.items())
        },
        "completion_assumed_per_attempt": COMPLETION_ASSUMED,
    }
