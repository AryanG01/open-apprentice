"""Plan 5 orchestration and scoring (evaluator side; spec 7).

Per episode and system: the learner-visible file and the private episode go into separate temporary folders; the learner
runs as its own process (audit hook installed, scrubbed environment) and talks to the teacher simulator, a third process
holding the private episode; the evaluator scores only after the learner has exited, on three fresh scoring documents
the learner never saw. Axes stay separate: a row carries one terminal outcome and its diagnostics, never a merged score.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from fractions import Fraction as F
from pathlib import Path
from typing import Any, Optional

from open_apprentice.concepts.rules import RuleError, evaluate_rule
from open_apprentice.evaluation.battery_v2 import (
    REPO,
    SCORING_VERSION,
    Episode,
    episode_from_json,
    episode_to_json,
    learner_view,
    verify_frozen,
)
from open_apprentice.evaluation.labels import check_after
from open_apprentice.evaluation.metrics import Row
from open_apprentice.evaluation.specs_v2 import VSpec, oracle_v
from open_apprentice.teaching import codec
from open_apprentice.teaching.step import _forbidden_effect

OUTCOMES = (
    "correct_complete",
    "wrong_commit",
    "appropriate_refusal",
    "unnecessary_abstention",
    "error",
)
TOL = F(1, 2)
BATTERY_DIRS = {
    "dev": REPO / "benchmarks/development/battery",
    "final": REPO / "benchmarks/final/battery",
}
WALL_S = 300
FORBIDDEN_ENV = ("benchmarks/final", ".private.json")


@dataclass(frozen=True)
class RowV2(Row):
    stratum: str = ""
    spec_kind: str = ""
    clarification_required: bool = False
    terminal_outcome: str = "error"
    diagnostics: dict = field(default_factory=dict)
    correction: Optional[dict] = None
    release_blocking: list = field(default_factory=list)
    model: str = "Fixture"
    reason: Optional[str] = None
    correction_policy: Optional[str] = None


# ---------------------------------------------------------------------------------------------------- scoring


def _apply(rule: list, scene: dict) -> Optional[dict]:
    try:
        st = evaluate_rule(rule, scene["objects"], scene["canvas"])
    except RuleError:
        return None
    return {
        "objects": [
            dict(o, **{k: st[o["id"]][k] for k in ("x", "y", "w", "h")}) for o in scene["objects"]
        ],
        "canvas": scene["canvas"],
    }


def _check(rule: list, spec: VSpec, scenes: list[dict]) -> dict:
    """Intent, preservation and layout on each fresh document, kept separate."""
    per = []
    for scene in scenes:
        after = _apply(rule, scene)
        if after is None:
            per.append({"intent": False, "preservation": False, "layout": False, "runs": False})
            continue
        r = check_after(scene, after, oracle_v(spec, scene))
        per.append({k: r[k] for k in ("intent", "preservation", "layout")} | {"runs": True})
    return {
        "per_scene": per,
        "complete": all(all(p.values()) for p in per),
        "preservation_accepted": any(p["runs"] and not p["preservation"] for p in per),
    }


def _final_positions(spec: VSpec, scene: dict) -> dict:
    moved = oracle_v(spec, scene)
    return {
        o["id"]: moved.get(o["id"], (F(o["x"]), F(o["y"])))
        for o in scene["objects"]
        if o["kind"] == "label"
    }


def _close(a: tuple, b: tuple) -> bool:
    return abs(F(a[0]) - b[0]) <= TOL and abs(F(a[1]) - b[1]) <= TOL


def _correction_check(rule: list, ep: Episode) -> dict:
    """Changed scope (labels the corrected behaviour moves differently) and retention (every other label keeps the base
    behaviour), on the scoring documents, reported separately."""
    c = ep.correction
    scope_ok = retention_ok = preserved = True
    for scene in ep.scoring_scenes:
        after = _apply(rule, scene)
        if after is None:
            return {"scope_ok": False, "retention_ok": False, "preservation_ok": False}
        got = {o["id"]: (o["x"], o["y"]) for o in after["objects"] if o["kind"] == "label"}
        base, new = _final_positions(ep.spec, scene), _final_positions(c["spec"], scene)
        for lid in base:
            if base[lid] != new[lid]:
                scope_ok &= _close(got[lid], new[lid])
            else:
                retention_ok &= _close(got[lid], base[lid])
        before = {o["id"]: o for o in scene["objects"]}
        preserved &= all(
            (o["w"], o["h"]) == (before[o["id"]]["w"], before[o["id"]]["h"])
            and (
                o["kind"] == "label"
                or (o["x"], o["y"]) == (before[o["id"]]["x"], before[o["id"]]["y"])
            )
            for o in after["objects"]
        )
    return {"scope_ok": scope_ok, "retention_ok": retention_ok, "preservation_ok": preserved}


def _learning(ep: Episode, outcome: dict, spec: VSpec) -> tuple[str, dict]:
    status = outcome["status"]
    if outcome.get("boundary_violation") or status not in ("committed", "abstained"):
        return "error", {}
    sub = ep.meta.get("subtype")
    refusal_expected = ep.stratum in ("inconsistent", "unsupported")
    if status == "abstained":
        return ("appropriate_refusal" if refusal_expected else "unnecessary_abstention"), {}
    rule = (outcome.get("program") or {}).get("rule")
    if not rule:
        return "error", {}
    check = _check(rule, spec, ep.scoring_scenes)
    if ep.stratum == "inconsistent" or sub in ("forced_overlap", "unsupported_structure"):
        # an invented resolution of a contradiction, or a convention applied where it cannot be applied validly
        return "wrong_commit", check
    return ("correct_complete" if check["complete"] else "wrong_commit"), check


def score(ep: Episode, outcome: dict) -> dict:
    """Terminal outcome (spec 7) of one learner outcome, plus the evaluator-private checks behind it."""
    violated = bool(
        outcome.get("boundary_violation")
        or outcome.get("boundary_refusal")
        or outcome.get("evaluator_modules")
    )
    blocking = ["boundary_violation"] if violated else []
    outcome = dict(outcome, boundary_violation=violated)
    terminal, check = _learning(ep, outcome, ep.spec)
    if check.get("preservation_accepted"):
        blocking.append("accepted_preservation_violation")
    result: dict[str, Any] = {"terminal_outcome": terminal, "check": check, "correction": None}
    if ep.stratum == "sequential":
        c = ep.correction
        acquired = terminal == "correct_complete"
        corr: dict[str, Any] = {"kind": c["kind"], "acquired": acquired, "success": None}
        co = outcome.get("correction") or {}
        corr["status"] = co.get("status")
        if acquired:
            st = co.get("status")
            if c["kind"] in ("override", "accidental"):
                corr["success"] = (
                    st == {"override": "override", "accidental": "dismissed"}[c["kind"]]
                )
            elif c["kind"] == "conflict":
                corr["success"] = st in ("abstained", "activation_rejected")
            elif st == "activated" and (co.get("program") or {}).get("rule"):
                corr |= _correction_check(co["program"]["rule"], ep)
                corr["success"] = (
                    corr["scope_ok"] and corr["retention_ok"] and corr["preservation_ok"]
                )
                if not corr["retention_ok"]:
                    blocking.append("unexplained_retention_regression")
                if not corr["preservation_ok"]:
                    blocking.append("accepted_preservation_violation")
            else:
                corr["success"] = False
            if corr["success"]:
                terminal = "correct_complete"
            elif st == "error" or st is None:
                terminal = "error"
            elif st == "activated" or (c["kind"] == "conflict" and st != "abstained"):
                terminal = "wrong_commit"
            elif c["kind"] in ("compatible", "superseding"):
                terminal = "unnecessary_abstention"
            else:
                terminal = "wrong_commit"
        result["correction"] = corr
        result["terminal_outcome"] = terminal
    result["release_blocking"] = blocking
    return result


def _diagnostics(outcome: dict) -> dict:
    evs = outcome.get("events") or []
    scenes = [e["payload"]["scene"] for e in evs if e["type"] == "SceneRegistered"]
    unsafe = 0
    for e in evs:
        if e["type"] == "ModelProposalReturned":
            for c in e["payload"]["candidates"]:
                if any(_forbidden_effect(c["rule"], _scene(s)) for s in scenes):
                    unsafe += 1
    reasons = [
        str(e["payload"].get("reason", ""))
        for e in evs
        if e["type"] in ("Abstained", "Errored", "ActivationRejected", "ModelCallFailed")
    ]
    return {
        "unsafe_proposal_blocked": unsafe,
        "preservation_violation_blocked": sum(
            1 for r in reasons if re.search(r"scope|regression|preserv", r)
        ),
        "provider_failures": sum(1 for e in evs if e["type"] == "ModelCallFailed")
        + sum(1 for e in evs if e["type"] == "AgentTurn" and e["payload"].get("provider_failure")),
        "protocol_failures": sum(1 for r in reasons if r.startswith("protocol")),
        "parse_failures": sum(
            int(e["payload"].get("malformed", 0))
            for e in evs
            if e["type"] == "ModelProposalReturned"
        )
        + sum(1 for e in evs if e["type"] == "AgentTurn" and e["payload"].get("parse_failure")),
        "budget_exhausted": any("budget" in r for r in reasons),
    }


def _scene(payload: dict) -> dict:
    from open_apprentice.teaching.constraints import scene_from_payload

    return scene_from_payload(payload)


# ---------------------------------------------------------------------------------------------------- running


def _learner_env() -> dict:
    env = {k: v for k, v in os.environ.items() if not any(m in v for m in FORBIDDEN_ENV)}
    paths = [str(REPO / "src"), *(p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p)]
    env["PYTHONPATH"] = os.pathsep.join(os.path.abspath(p) for p in paths)
    return env


def run_learner(
    ep: Episode, system: str, mode: str, seed: int, keep: Path, wall_s: int = WALL_S
) -> tuple[dict, float]:
    ldir, pdir = Path(tempfile.mkdtemp(prefix="oa-l-")), Path(tempfile.mkdtemp(prefix="oa-p-"))
    try:
        lf, pf = ldir / "episode.json", pdir / "episode.private.json"
        lf.write_bytes(codec.dumps(learner_view(ep)))
        pf.write_bytes(codec.dumps(episode_to_json(ep)))
        tlog = pdir / "teacher.jsonl"
        teacher = subprocess.Popen(
            [sys.executable, "-m", "open_apprentice.evaluation.teacher_sim", str(pf), str(tlog)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            env=_learner_env(),
        )
        assert teacher.stdin is not None and teacher.stdout is not None
        fds = (
            teacher.stdout.fileno(),
            teacher.stdin.fileno(),
        )  # the learner gets pipe ends, never the path
        out = ldir / "outcome.json"
        argv = [sys.executable, "-m", "open_apprentice.learner.main", "--episode", str(lf)]
        argv += ["--system", system, "--teacher-fds", f"{fds[0]},{fds[1]}", "--mode", mode]
        argv += ["--seed", str(seed), "--out", str(out)]
        t0 = time.monotonic()
        try:
            r = subprocess.run(
                argv,
                env=_learner_env(),
                capture_output=True,
                text=True,
                timeout=wall_s,
                pass_fds=fds,
            )
            stderr = r.stderr
        except subprocess.TimeoutExpired:
            stderr = "wall-clock limit"
        finally:
            teacher.stdin.close()
            try:
                teacher.wait(timeout=10)
            except subprocess.TimeoutExpired:
                teacher.kill()
        wall = time.monotonic() - t0
        if out.exists():
            outcome = json.loads(out.read_text())
        else:
            outcome = {"status": "error", "reason": f"no outcome: {stderr[-300:]}", "events": []}
        keep.mkdir(parents=True, exist_ok=True)
        (keep / "outcome.json").write_text(json.dumps(outcome, default=str))
        if tlog.exists():
            shutil.copy(tlog, keep / "teacher.jsonl")
        (keep / "stderr.txt").write_text(stderr[-20_000:])
        return outcome, wall
    finally:
        shutil.rmtree(ldir, ignore_errors=True)
        shutil.rmtree(pdir, ignore_errors=True)


def run_episode(
    ep: Episode,
    system: str,
    mode: str,
    seed: int,
    repeat: int,
    out_dir: Path,
    model: str = "Fixture",
) -> RowV2:
    keep = Path(out_dir) / "episodes" / f"{ep.id}-{system}-r{repeat}"
    outcome, wall = run_learner(ep, system, mode, seed, keep)
    s = score(ep, outcome)
    evs = outcome.get("events") or []
    usage = outcome.get("usage") or {}
    spend = outcome.get("spend") or {}
    terminal = s["terminal_outcome"]
    committed = outcome.get("status") == "committed"
    return RowV2(
        episode=ep.id,
        rep=repeat,
        method=system,
        task_id=ep.id,
        stage=ep.stratum,
        committed=committed,
        claimed_success=committed,
        correct=(terminal == "correct_complete") if committed else None,
        abstained=outcome.get("status") == "abstained",
        failure=outcome.get("reason") if terminal == "error" else None,
        tokens=int(usage.get("prompt_tokens", 0)) + int(usage.get("completion_tokens", 0)),
        calls=sum(
            1
            for e in evs
            if e["type"] == "ActionIssued"
            and e["payload"]["kind"] in ("RequestModelProposal", "AgentTurn")
        ),
        teacher_interactions=sum(1 for e in evs if e["type"] == "RequestIssued"),
        wall_s=round(wall, 3),
        usd=float(F(spend.get("total", 0))) if spend else None,
        origin="mock" if mode == "mock" else "live",
        stratum=ep.stratum,
        spec_kind=ep.spec.kind,
        clarification_required=ep.clarification_required,
        terminal_outcome=terminal,
        diagnostics=_diagnostics(outcome),
        correction=s["correction"],
        release_blocking=s["release_blocking"],
        model=model,
        reason=outcome.get("reason"),
        correction_policy=outcome.get("correction_policy"),
    )


def load_split(battery_dir: Path, expected: Optional[dict] = None) -> list[Episode]:
    """The frozen episodes, after every hash has been re-checked."""
    verify_frozen(battery_dir, expected)
    manifest = json.loads((Path(battery_dir) / "manifest.private.json").read_text())
    return [
        episode_from_json(
            json.loads((Path(battery_dir) / f"episodes/{e['id']}.private.json").read_text())
        )
        for e in manifest["episodes"]
    ]


def run_battery(
    split: str,
    systems: list[str],
    repeats: int,
    mode: str,
    out_root: Path = REPO / "results/eval_v2",
    battery_dir: Optional[Path] = None,
    episodes: Optional[list[str]] = None,
    seed: int = 0,
    run_id: Optional[str] = None,
) -> Path:
    if mode != "mock":
        raise PermissionError("live runs start only through the approved-manifest gate")
    if split == "final":
        raise PermissionError("the final split runs only as the gated live run, once")
    eps = load_split(battery_dir or BATTERY_DIRS[split])
    if episodes:
        eps = [e for e in eps if e.id in set(episodes)]
    run_id = run_id or f"{split}-{mode}-{time.strftime('%Y%m%dT%H%M%S')}"
    out = Path(out_root) / run_id
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    with open(out / "rows.jsonl", "w") as f:
        for r in range(repeats):
            for ep in eps:
                for system in systems:
                    row = run_episode(ep, system, mode, seed + r, r, out)
                    f.write(json.dumps(asdict(row), default=str) + "\n")
                    f.flush()
    manifest = {
        "run_id": run_id,
        "split": split,
        "mode": mode,
        "model": "Fixture",
        "systems": systems,
        "repeats": repeats,
        "seed": seed,
        "episodes": [e.id for e in eps],
        "scoring_version": SCORING_VERSION,
        "wall_s": round(time.monotonic() - t0, 1),
        "note": (
            "offline: every row is origin=mock, model=Fixture; not a model result"
            if mode == "mock"
            else ""
        ),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return out
