"""Behaviour difference between the active program and a correction candidate, and the retention report stored with every
new version. Claims are bounded: "no unexplained regressions on the checked evidence and scenes". Spec 5."""

from __future__ import annotations

from open_apprentice.teaching.evidence import EvidenceItem, item_fits
from open_apprentice.teaching.scope import members
from open_apprentice.teaching.step import run_output


def behaviour_diff(
    base_rule: list,
    cand_rule: list,
    scenes: dict[str, dict],
    selector: str,
    exceptions: frozenset[tuple[str, str]],
) -> dict:
    out: dict[str, list[tuple[str, str]]] = {"in_scope": [], "exception": [], "unexplained": []}
    for sid in sorted(scenes):
        sc = scenes[sid]
        a, b = run_output(base_rule, sc) or {}, run_output(cand_rule, sc) or {}
        inside = members(selector, sc)
        for lid in sorted(set(a) | set(b)):
            if a.get(lid) == b.get(lid):
                continue
            key = (sid, lid)
            if lid in inside:
                out["in_scope"].append(key)
            elif key in exceptions:
                out["exception"].append(key)
            else:
                out["unexplained"].append(key)
    return out


def retention_report(
    cand_rule: list,
    active: list[EvidenceItem],
    superseded: dict[str, dict],
    replacements: list[EvidenceItem],
    diff: dict,
    scenes_searched: int,
) -> dict:
    retained = [{"id": it.id, "ok": item_fits(cand_rule, it)[0]} for it in active]
    return {
        "retained": retained,
        "superseded": [{"id": k, **v} for k, v in sorted(superseded.items())],
        "replacements": [r.id for r in replacements],
        "scope_violations": list(diff["unexplained"]),
        "unexplained_regressions": [r["id"] for r in retained if not r["ok"]],
        "coverage": {"scenes": scenes_searched},
        "claim": "no unexplained regressions on the checked evidence and scenes",
    }
