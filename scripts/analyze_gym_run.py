"""Summarise a NeMo Gym rollouts file for the calibrated-asking environment and compare it with the scripted policies on the SAME tasks.
Rollouts come back out of order, so they are matched to inputs by _ng_task_index. Writes compact rows (no raw prompts) and a summary.
Usage: python scripts/analyze_gym_run.py gym/results/ultra results/gym_ultra"""

import json
import pathlib
import sys

COMPONENTS = ["correct", "held_out", "asking", "not_confidently_wrong", "economy"]
IN_RATE, OUT_RATE = 1e-6, 3e-6  # configured Nebius rates, owner-entered and unverified


def main(run_dir: str, out_dir: str) -> None:
    run, out = pathlib.Path(run_dir), pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rollouts = [
        json.loads(line)
        for line in (run / "rollouts.jsonl").read_text().splitlines()
        if line.strip()
    ]
    inputs = {}
    for i, line in enumerate((run / "rollouts_materialized_inputs.jsonl").read_text().splitlines()):
        if line.strip():
            m = json.loads(line)
            inputs[m.get("_ng_task_index", i)] = m
    scripted = [
        json.loads(line)
        for line in pathlib.Path("results/asking_baselines/rows.jsonl").read_text().splitlines()
    ]
    rows = []
    for r in rollouts:
        m = inputs[r["_ng_task_index"]]
        usage = (r.get("response") or {}).get("usage") or {}
        calls = [o for o in r["response"]["output"] if o.get("type") == "function_call"]
        commit = next(
            (json.loads(c["arguments"]).get("rule") for c in calls if c["name"] == "commit"), None
        )
        rows.append(
            {
                "task_index": r["_ng_task_index"],
                "episode": m["index"],
                "kind": m["kind"],
                "ambiguous": r["ambiguous"],
                "components": {c: r[c] for c in COMPONENTS},
                "committed": r["committed"],
                "abstained": r["abstained"],
                "asks_used": r["asks_used"],
                "tool_calls": [c["name"] for c in calls],
                "committed_rule": commit,
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "est_cost_usd_configured_rates": round(
                    (usage.get("input_tokens") or 0) * IN_RATE
                    + (usage.get("output_tokens") or 0) * OUT_RATE,
                    4,
                ),
            }
        )
    rows.sort(key=lambda x: x["task_index"])
    (out / "rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    keys = {(r["episode"], r["kind"]) for r in rows}

    def mean(rs, c):
        return (
            round(sum(x["components"][c] if "components" in x else 0 for x in rs) / len(rs), 3)
            if rs
            else None
        )

    table = {}
    for label, rs in (
        ("nemotron_3_ultra", rows),
        *[
            (p, [s for s in scripted if s["policy"] == p and (s["index"], s["kind"]) in keys])
            for p in ("never_ask", "always_ask", "calibrated", "always_abstain")
        ],
    ):
        table[label] = {
            g: {"n": len(sub), **{c: mean(sub, c) for c in COMPONENTS}}
            for g, sub in (
                ("all", rs),
                ("ambiguous", [x for x in rs if x["ambiguous"]]),
                ("unambiguous", [x for x in rs if not x["ambiguous"]]),
            )
        }
    cost = sum(r["est_cost_usd_configured_rates"] for r in rows)
    summary = {
        "tasks_completed": len(rows),
        "tasks_planned": 24,
        "est_cost_usd_configured_rates": round(cost, 3),
        "est_cost_usd_conservative_4_per_m": round(
            sum(((r["input_tokens"] or 0) + (r["output_tokens"] or 0)) * 4e-6 for r in rows), 3
        ),
        "tokens": {
            "input": sum(r["input_tokens"] or 0 for r in rows),
            "output": sum(r["output_tokens"] or 0 for r in rows),
        },
        "table": table,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(
        f"{len(rows)} of 24 tasks; est cost ${summary['est_cost_usd_configured_rates']} (conservative ${summary['est_cost_usd_conservative_4_per_m']}); tokens {summary['tokens']}"
    )
    for g in ("all", "ambiguous", "unambiguous"):
        print(f"\n{g} (Ultra n={table['nemotron_3_ultra'][g]['n']})")
        print(f"{'policy':<18}" + "".join(f"{c:>23}" for c in COMPONENTS))
        for p, t in table.items():
            print(f"{p:<18}" + "".join(f"{t[g][c]!s:>23}" for c in COMPONENTS))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
