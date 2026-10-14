"""Real-file check: teach a placement intention from a demonstration made on ONE SVG file, apply the learned rule to the OTHER
SVG files, and judge the patched files. Model-free with --reference, live Nemotron otherwise (capped, shared ledger).

Per application: the rule becomes a typed patch on the target file (byte-exact, only label x/y), the patched SVG is re-parsed,
and the independent checker compares the re-parsed scene with the oracle (intent), the untouched boxes and labels
(preservation) and overlaps/canvas (layout). Boxes of labels are estimated from font size (see svg/labels_io.py).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys
from fractions import Fraction as F

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from open_apprentice.budget import Ledger, Limits  # noqa: E402
from open_apprentice.concepts.label_teaching import teach  # noqa: E402
from open_apprentice.evaluation import spend  # noqa: E402
from open_apprentice.evaluation.label_episodes import GATE_INTENTS  # noqa: E402
from open_apprentice.evaluation.label_reference import ReferenceProvider  # noqa: E402
from open_apprentice.evaluation.labels import (
    apply_oracle,
    check_after,
    make_scene,
    oracle,
)  # noqa: E402
from open_apprentice.svg.labels_io import (
    LabelsNotApplicable,
    apply_rule_to_svg,
    scene_from_svg,
)  # noqa: E402

SAMPLES = pathlib.Path("src/open_apprentice/svg/samples")
FILES = ["pipeline", "crowded-services", "mixed-layout"]


def shows(intent: str, spec, scene: dict) -> bool:
    if intent == "conditional":
        return any(
            oracle(spec, scene).get(k) != v
            for k, v in oracle(type(spec)(spec.primary, None, spec.scope, spec.gap), scene).items()
        )
    if intent == "scope":
        return any(o["role"] == "warning" for o in scene["objects"])
    return True


def judge(text: str, rule: list, spec) -> dict:
    out = apply_rule_to_svg(text, rule)
    before = out["scene"]
    after, _ = scene_from_svg(out["text"])  # round trip through the patched file
    r = check_after(before, after, oracle(spec, before))
    return {
        "intent": r["intent"],
        "preservation": r["preservation"],
        "layout": r["layout"],
        "problems": r["problems"],
        "unrelated_byte_changes": out["result"].unrelated_byte_changes if out["result"] else 0,
        "moved": len(out["targets"]),
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", action="store_true")
    ap.add_argument("--cap-usd", type=float, default=0)
    ap.add_argument("--run-id", default="realfile-1")
    a = ap.parse_args()
    texts = {f: (SAMPLES / f"{f}.svg").read_text() for f in FILES}
    scenes = {f: scene_from_svg(t)[0] for f, t in texts.items()}
    prov = None
    if not a.reference:
        if a.cap_usd <= 0:
            raise SystemExit("--cap-usd is required for live runs")
        import run_label_experiment as R

        prov = spend.SpendGuard(
            R.make_live_provider(R.DEFAULT_MODEL, "low", 32000),
            run_id=a.run_id,
            run_cap_usd=a.cap_usd,
            merge_system=True,
        )
    rows = []
    for intent, spec in GATE_INTENTS.items():
        for demo_file in FILES:
            if not shows(intent, spec, scenes[demo_file]):
                continue
            demo = (
                scenes[demo_file],
                apply_oracle(scenes[demo_file], oracle(spec, scenes[demo_file])),
            )
            batch = [make_scene(70_000 + i, 4 + i, warnings=i % 3) for i in range(3)]
            teacher = lambda sc, s=spec: apply_oracle(sc, oracle(s, sc))  # noqa: E731
            p = ReferenceProvider() if a.reference else prov
            res = await teach(p, Ledger(Limits(tokens=10**7, calls=1000)), [demo], batch, teacher)
            for target in FILES:
                if target == demo_file:
                    continue
                row = {"intent": intent, "demo": demo_file, "target": target, "status": res.status}
                if res.status == "committed":
                    try:
                        row.update(judge(texts[target], res.rule, spec))
                        row["correct"] = (
                            all(row[k] for k in ("intent", "preservation", "layout"))
                            and not row["unrelated_byte_changes"]
                        )
                    except LabelsNotApplicable as e:
                        row.update(correct=False, error=str(e))
                else:
                    row.update(correct=False, reason=res.reason)
                rows.append(row)
                print(
                    f"{intent:12} demo={demo_file:17} -> {target:17} {res.status:10} correct={row['correct']}"
                )
    if prov:
        await prov.aclose()
    out = pathlib.Path("results/redesign") / a.run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "realfile.json").write_text(json.dumps(rows, indent=1, default=str))
    print(f"{sum(r['correct'] for r in rows)}/{len(rows)} applications correct")


if __name__ == "__main__":
    asyncio.run(main())
