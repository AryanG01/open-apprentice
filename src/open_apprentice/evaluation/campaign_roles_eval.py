"""The pre-registered role-mapping comparison (docs/evaluation/campaign_roles_protocol.md): heuristic (A), Nemotron raw
(B), the shipped hybrid (C, reusing B's call) and a strong-prompt Nemotron that may abstain (D), on untagged banners.
Scoring is fixed by the protocol; the live run goes through SpendGuard with a run cap."""

from __future__ import annotations

import json
import pathlib
import time

from open_apprentice.budget import Ledger, Limits
from open_apprentice.campaign.limits import ROLES
from open_apprentice.campaign.model import call_model
from open_apprentice.campaign.roles import (
    heuristic_roles,
    opaque_ids,
    propose_roles,
    role_candidates,
)
from open_apprentice.providers.base import Provider, StrictModel

STRONG_PROMPT = pathlib.Path(__file__).resolve().parents[3] / "prompts" / "campaign_roles_strong.md"
ARMS = ("A", "B", "C", "D")
ARM_NAMES = {
    "A": "heuristic",
    "B": "Nemotron, shipped prompt, raw",
    "C": "shipped hybrid (Nemotron, checker, heuristic fallback)",
    "D": "Nemotron, strong prompt, may abstain",
}


class StrongOut(StrictModel):
    roles: dict[str, str]
    abstain: bool
    reason: str


def load_cases(directory: pathlib.Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json"))]


def _strip(scene: dict) -> tuple[dict, dict]:
    gold = {n["id"]: n["role"] for n in scene["nodes"] if n.get("role")}
    untagged = {
        **scene,
        "nodes": [{k: v for k, v in n.items() if k != "role"} for n in scene["nodes"]],
    }
    return untagged, gold


def complete(m: dict) -> bool:
    return len(m) == len(ROLES) and set(m.values()) == set(ROLES)


def score(pred: dict, gold: dict, expect: str) -> dict:
    full = complete(pred)
    exact = (pred == gold) if expect == "map" else not full
    wrong = sum(pred.get(i) != gold.get(i) for i in set(pred) | set(gold))
    return {
        "exact": exact,
        "false_confident": full and pred != gold,
        "corrections": wrong if expect == "map" else None,
    }


def summarize(rows: list[dict]) -> dict:
    """Macro-F1 over the roles on map cases; a layer given the wrong role counts against both roles."""
    f1 = []
    for r in ROLES:
        tp = fp = fn = 0
        for row in rows:
            if row["expect"] != "map":
                continue
            g = next((i for i, v in row["gold"].items() if v == r), None)
            p = next((i for i, v in row["pred"].items() if v == r), None)
            if p is not None and p == g:
                tp += 1
            else:
                fp += p is not None
                fn += g is not None
        f1.append(2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 1.0)
    return {"macro_f1": sum(f1) / len(f1)}


async def run_cases(
    provider: Provider, cases: list[dict], ledger: Ledger | None = None
) -> list[dict]:
    ledger = ledger or Ledger(Limits(tokens=600_000, calls=120))
    rows = []
    for case in cases:
        art = case.get("artboard", "banner")
        scene, gold = _strip(case["scene"])
        t0 = time.monotonic()
        c = await propose_roles(provider, ledger, scene, art)
        c_s = time.monotonic() - t0
        t0 = time.monotonic()
        d = await call_model(
            provider, ledger, role="campaign_roles_strong", prompt=STRONG_PROMPT,
            payload={"layers": role_candidates(scene, art)}, schema=StrongOut, max_tokens=1500,
        )  # fmt: skip
        d_s = time.monotonic() - t0
        back = {v: k for k, v in opaque_ids(scene, art).items()}
        d_map = (
            {}
            if d.parsed is None or d.parsed.abstain
            else {back.get(i, i): r for i, r in d.parsed.roles.items()}
        )
        preds = {
            "A": heuristic_roles(scene, art),
            "B": c.proposed or {},
            "C": c.mapping,
            "D": d_map,
        }
        rows.append(
            {
                "id": case["id"],
                "category": case["category"],
                "expect": case["expect"],
                "gold": gold,
                "preds": preds,
                "arms": {a: score(preds[a], gold, case["expect"]) for a in ARMS},
                "c_origin": c.origin,
                "c_problems": c.problems,
                "d_reason": None if d.parsed is None else d.parsed.reason,
                "d_error": d.error,
                "seconds": {"BC": round(c_s, 2), "D": round(d_s, 2)},
            }
        )
    return rows


def totals(rows: list[dict]) -> dict:
    out = {}
    for a in ARMS:
        arm = [r["arms"][a] for r in rows]
        corr = [s["corrections"] for s in arm if s["corrections"] is not None]
        out[a] = {
            "exact": sum(s["exact"] for s in arm),
            "false_confident": sum(s["false_confident"] for s in arm),
            "corrections": sum(corr),
            **summarize(
                [{"expect": r["expect"], "gold": r["gold"], "pred": r["preds"][a]} for r in rows]
            ),
        }
    return out


def verdicts(t: dict) -> list[str]:
    """The protocol's three bars, applied mechanically."""
    a, b, c, d = (t[k] for k in ARMS)
    return [
        "Bar 1 (Nemotron improves role mapping): "
        + (
            "MET"
            if c["exact"] >= a["exact"] + 3 and c["false_confident"] <= a["false_confident"]
            else "NOT MET"
        ),
        "Bar 2 (the checker adds safety): "
        + ("MET" if c["false_confident"] < b["false_confident"] else "NOT MET"),
        "Bar 3 (a better prompt beats the shipped one): "
        + ("MET" if d["exact"] >= c["exact"] + 3 else "NOT MET"),
    ]


def render_markdown(
    rows: list[dict], *, model: str, spent_usd: float, calls: int, manifest: str
) -> str:
    t = totals(rows)
    n, n_map = len(rows), sum(r["expect"] == "map" for r in rows)
    lines = [
        "# Campaign role mapping: result of the pre-registered comparison",
        "",
        f"Protocol: `campaign_roles_protocol.md` · set: {n} banners ({n_map} map, {n - n_map} abstain), manifest "
        f"`{manifest[:16]}…` · model `{model}` · {calls} calls · ${spent_usd:.3f} (ledger)",
        "",
        f"| arm | exact (of {n}) | false confident | corrections ({n_map} map cases) | macro-F1 |",
        "|---|---|---|---|---|",
    ]
    for a in ARMS:
        x = t[a]
        lines.append(
            f"| {a}: {ARM_NAMES[a]} | {x['exact']} | {x['false_confident']} | {x['corrections']} | {x['macro_f1']:.3f} |"
        )
    lines += [
        "",
        *[f"- {v}" for v in verdicts(t)],
        "",
        "## Per banner (✓ exact, ✗ wrong, ! false confident)",
        "",
    ]
    lines += [
        "| banner | category | A | B | C | D | C used | why C fell back / D abstained |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        cell = lambda s: "✓" if s["exact"] else ("!" if s["false_confident"] else "✗")  # noqa: E731
        why = "; ".join(r["c_problems"])[:120] or "-"
        if r["d_reason"]:
            why += f" / D: {r['d_reason'][:80]}"
        lines.append(
            f"| {r['id']} | {r['category']} | "
            + " | ".join(cell(r["arms"][a]) for a in ARMS)
            + f" | {r['c_origin']} | {why} |"
        )
    return "\n".join(lines) + "\n"
