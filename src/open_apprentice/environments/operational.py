"""Operational checker (spec 10.3): coarse PUBLIC feedback from public observations only.

Uses observe_geometry output (a public tool). It is NOT the final verifier and must not be confused
with it: it cannot see native state or hidden variants, and returns only check names + pass/fail.
"""

from __future__ import annotations

TOL = 0.5


def check_gap_row_public(bounds: list[dict], task_view: dict) -> dict:
    ids, p = task_view["selected_ids"], task_view["parameters"]
    b = {x["id"]: x for x in bounds}
    if any(i not in b for i in ids):
        return {"passed": False, "failed": ["objects_observed"]}
    failed = []
    order = sorted(ids, key=lambda i: b[i]["left"])
    if order != ids:
        failed.append("order")
    gaps = [b[y]["left"] - (b[x]["left"] + b[x]["width"]) for x, y in zip(ids, ids[1:])]
    if any(abs(g - p["gap_px"]) > TOL for g in gaps):
        failed.append("edge_gaps")
    if abs(b[ids[0]]["left"] - p["left_px"]) > TOL:
        failed.append("left_edge")
    if any(abs(b[i]["top"] - p["top_px"]) > TOL for i in ids):
        failed.append("top_alignment")
    return {"passed": not failed, "failed": failed}
