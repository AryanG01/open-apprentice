"""Report generation from stored rows (spec 20). Numbers are computed, never typed. Anything not produced by a
live run is stamped so it cannot be mistaken for a result."""

from __future__ import annotations

import json

from open_apprentice.evaluation.metrics import Row, method_summary, paired_cluster_bootstrap

TRANSFER_STAGES = {"transfer", "composition"}
# Prospective quality gates from spec 27.5: goals, NOT promised results and NOT a score.
GATES = {
    "transfer_composition_success_min": 0.90,
    "improvement_over_strongest_baseline_min_pp": 10.0,
}


class EmptyResults(Exception):
    pass


def build_report(
    rows: list[Row],
    methods: list[str],
    primary: tuple[str, str],
    config_id: str,
    allow_mock: bool = False,
) -> dict:
    if not rows:
        raise EmptyResults("no stored rows: refusing to produce a report")
    origins = sorted({r.origin for r in rows})
    mock = any(
        o in ("mock", "replay") for o in origins
    )  # "reference" = real execution by a non-model method
    if mock and not allow_mock:
        raise EmptyResults(
            f"rows include non-live origins {origins}; pass allow_mock=True to render a clearly labelled plumbing report"
        )
    summaries = {m: method_summary(rows, m) for m in methods}
    on_tc = {m: method_summary(rows, m, TRANSFER_STAGES) for m in methods}
    boot = paired_cluster_bootstrap(rows, primary[0], primary[1], TRANSFER_STAGES)
    strongest_baseline = max(
        (m for m in methods if m != primary[0]),
        key=lambda m: on_tc[m]["success"]["rate"] or 0.0,
        default=None,
    )
    vs_strongest = (
        paired_cluster_bootstrap(rows, primary[0], strongest_baseline, TRANSFER_STAGES)
        if strongest_baseline
        else None
    )
    full_rate = on_tc[primary[0]]["success"]["rate"]
    gates = {
        "status": "not_evaluated_on_non_live_rows" if mock else "evaluated",
        "caveat": "prospective goals from spec 27.5; passing them would support considering an exceptional score, not guarantee one",
    }
    if not mock:
        gates["transfer_composition_success"] = {
            "observed": full_rate,
            "goal": GATES["transfer_composition_success_min"],
            "met": full_rate is not None and full_rate >= GATES["transfer_composition_success_min"],
        }
        if vs_strongest and vs_strongest["ci95"]:
            gates["improvement_over_strongest_baseline_pp"] = {
                "baseline": strongest_baseline,
                "observed_pp": 100 * vs_strongest["diff"],
                "ci95_pp": [100 * x for x in vs_strongest["ci95"]],
                "goal_pp": GATES["improvement_over_strongest_baseline_min_pp"],
                "met": 100 * vs_strongest["diff"]
                >= GATES["improvement_over_strongest_baseline_min_pp"]
                and vs_strongest["ci95"][0] > 0,
            }
    return {
        "config": config_id,
        "origins": origins,
        "label": (
            "MOCK / SCRIPTED - PLUMBING CHECK ONLY, NOT A RESULT"
            if mock
            else "MEASURED (live model rows + non-model reference rows; split and n stated below)"
        ),
        "episodes": sorted({r.episode for r in rows}),
        "n_rows": len(rows),
        "methods_all_stages": summaries,
        "methods_transfer_and_composition": on_tc,
        "primary_comparison": boot,
        "primary_vs_strongest_baseline": vs_strongest,
        "gates_27_5": gates,
    }


def render_markdown(rep: dict) -> str:
    L = [
        f"# Report ({rep['config']})",
        f"**{rep['label']}**",
        "",
        f"Rows: {rep['n_rows']} over {len(rep['episodes'])} independent episodes. Repetitions do not add independent samples.",
        "",
        "| method | correct / scheduled (transfer+composition) | conditional | false success | failures |",
        "|---|---|---|---|---|",
    ]
    for m, s in rep["methods_transfer_and_composition"].items():
        su, co, fs = s["success"], s["conditional"], s["false_success"]
        L.append(
            f"| {m} | {su['correct']}/{su['scheduled']} | {co['correct']}/{co['committed']} | "
            f"{fs['false_successes']}/{fs['claimed_successes']} | {json.dumps(s['failures'])} |"
        )
    p = rep["primary_comparison"]
    L += [
        "",
        f"Primary: {p['a']} - {p['b']} over {p['n_episodes']} episodes: diff={p['diff']}, 95% CI={p['ci95']}. {p['note']}",
        "",
        f"Gates (spec 27.5, prospective): {rep['gates_27_5']['status']}. {rep['gates_27_5']['caveat']}",
    ]
    return "\n".join(L)
