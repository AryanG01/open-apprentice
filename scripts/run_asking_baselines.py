"""Run the four scripted policies over the development episodes of the calibrated-asking environment. Free: no model, no network.
Writes results/asking_baselines/rows.jsonl and summary.json; prints the per-component table split by ambiguous / unambiguous tasks."""

import json
import pathlib

from open_apprentice.evaluation.asking_baselines import POLICIES, run_policy

OUT = pathlib.Path("results/asking_baselines")
SPLIT, SEED, EPISODES = "development", 0, 12
COMPONENTS = ["correct", "held_out", "asking", "not_confidently_wrong", "economy"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [
        run_policy(p, SPLIT, SEED, i, k)
        for p in POLICIES
        for i in range(EPISODES)
        for k in ("badge", "spacing")
    ]
    (OUT / "rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    summary: dict = {}
    for policy in POLICIES:
        for group, pick in (("all", None), ("ambiguous", True), ("unambiguous", False)):
            rs = [
                r
                for r in rows
                if r["policy"] == policy and (pick is None or r["ambiguous"] == pick)
            ]
            summary.setdefault(policy, {})[group] = {
                "n": len(rs),
                **{c: round(sum(r["components"][c] for r in rs) / len(rs), 3) for c in COMPONENTS},
                "committed": round(sum(r["committed"] for r in rs) / len(rs), 3),
            }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1))
    for group in ("all", "ambiguous", "unambiguous"):
        n = next(iter(summary.values()))[group]["n"]
        print(f"\n{group} tasks (n={n} per policy)")
        print(f"{'policy':<16}" + "".join(f"{c:>23}" for c in COMPONENTS))
        for policy in POLICIES:
            print(
                f"{policy:<16}" + "".join(f"{summary[policy][group][c]:>23.3f}" for c in COMPONENTS)
            )


if __name__ == "__main__":
    main()
