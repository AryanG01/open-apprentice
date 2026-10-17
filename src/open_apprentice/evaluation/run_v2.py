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
from open_apprentice.drawio.parse import DrawioRefused
from open_apprentice.evaluation.battery_v2 import (
    REPO,
    SCORING_VERSION,
    Episode,
    episode_from_json,
    episode_to_json,
    learner_view,
    verify_frozen,
    vspec_from_json,
)
from open_apprentice.evaluation.labels import check_after
from open_apprentice.evaluation.metrics import Row
from open_apprentice.evaluation.real_files import publish_failures, real_file_episode
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
ATTEMPTS_OUT = re.compile(r"budget exhausted: \d+ provider attempts|provider: attempt budget")
REFUSAL_KINDS = (
    ("no acceptable program", "no_program"),
    ("unresolved disagreement", "unresolved_disagreement"),
    ("refusing to apply", "refused_layout"),
    ("unsupported structure", "unsupported_structure"),
    ("agent:", "agent_abstained"),
)
DOLLAR_STOP = re.compile(r"budget: reserving|provider: budget|BUDGET_EXHAUSTED\[usd\]")
BATTERY_DIRS = {
    "dev": REPO / "benchmarks/development/battery",
    "final": REPO / "benchmarks/final/battery",
}
WALL_S = 300
FINAL_HASHES = REPO / "docs/evaluation/battery_final.hashes.json"
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
    refusal_kind: Optional[str] = None


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
    # a run stopped by the dollar cap has no outcome (spec 7: a budget stop keeps partial results and reports
    # coverage); running out of the allowed ATTEMPTS is an error for every system (A's executor already records it
    # as Errored), never a refusal: nothing was surfaced
    reason = str(outcome.get("reason") or "")
    result["budget_stop"] = bool(DOLLAR_STOP.search(reason))
    result["attempts_exhausted"] = bool(ATTEMPTS_OUT.search(reason)) and not result["budget_stop"]
    if result["budget_stop"] or result["attempts_exhausted"]:
        result["terminal_outcome"] = "error"
    result["refusal_kind"] = (
        _refusal_kind(reason) if result["terminal_outcome"] == "appropriate_refusal" else None
    )
    return result


def _refusal_kind(reason: str) -> str:
    for pattern, kind in REFUSAL_KINDS:
        if pattern in reason:
            return kind
    return "other"


def _failure(s: dict, outcome: dict) -> Optional[str]:
    if s["budget_stop"]:
        return "budget_stop"
    if s["attempts_exhausted"]:
        return "attempts_exhausted"
    return outcome.get("reason") if s["terminal_outcome"] == "error" else None


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
        # correction effort (spec 3.7 budgets): B chooses its own steps, so it may use more provider calls than A
        "correction_proposer_calls": sum(
            1
            for e in evs
            if e.get("log") == "correct"
            and e["type"] == "ActionIssued"
            and e["payload"].get("kind") == "RequestModelProposal"
        ),
        "correction_agent_turns": sum(
            1 for e in evs if e.get("log") == "correct" and e["type"] == "AgentTurn"
        ),
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
    ep: Episode,
    system: str,
    mode: str,
    seed: int,
    keep: Path,
    wall_s: int = WALL_S,
    extra: tuple[str, ...] = (),
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
        argv += ["--seed", str(seed), "--out", str(out), *extra]
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
    extra: tuple[str, ...] = (),
    wall_s: int = WALL_S,
    engine_url: Optional[str] = None,
) -> RowV2:
    keep = Path(out_dir) / "episodes" / f"{ep.id}-{system}-r{repeat}"
    outcome, wall = run_learner(ep, system, mode, seed, keep, wall_s, extra)
    s = score(ep, outcome)
    published: list[str] = []
    rule = (outcome.get("program") or {}).get("rule")
    if ep.stratum == "real_file" and s["terminal_outcome"] == "correct_complete" and rule:
        if engine_url is None:
            raise RuntimeError(
                "real-file episodes are scored through the engine: no engine_url given"
            )
        published = publish_failures(ep, rule, engine_url)
        if published:
            s = dict(s, terminal_outcome="wrong_commit")
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
        failure=_failure(s, outcome),
        refusal_kind=s["refusal_kind"],
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
        diagnostics=_diagnostics(outcome) | ({"publish_failures": published} if published else {}),
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


LIVE_WALL_S = 3600  # a live call may take minutes (SpendGuard's per-call deadline is 420 s)
MIN_CALL_USD = 0.2  # the learner reserves this per call (32k completion floor + prompt at $4/M): below it nothing runs


def run_live_battery(
    manifest: dict,
    cap_usd: float,
    out_root: Path = REPO / "results/eval_v2",
    budget_root: Path = REPO / "results/redesign",
    model: str = "",
    run_id: Optional[str] = None,
    dotenv: Path = REPO / ".env",
    resume: bool = False,
    workers: int = 1,
    engine_url: Optional[str] = None,
) -> Path:
    """The approved manifest's runs, live (called only after the paid-run gate). Systems alternate per episode in a
    seeded order; each learner gets the run's total cap and its guard charges what this run id has already spent in
    the shared ledger; the run stops when no call can fit or on any boundary violation. Partial results are kept and
    the coverage is reported. `resume` continues an existing run id: rows that errored without spending anything
    (they never reached the model) are moved to rows.superseded.jsonl and re-run; every other row stands.
    """
    import random
    import threading
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

    from open_apprentice.providers.spend import spent_for_run

    run_id = run_id or f"cal-{manifest['manifest_id']}-{time.strftime('%Y%m%dT%H%M%S')}"
    wanted = list(manifest["task_ids"])
    adapter_refused: dict[str, str] = {}
    expected = None
    if (
        manifest["split"] == "final"
    ):  # the frozen final battery, checked against the committed hashes
        expected = json.loads(Path(FINAL_HASHES).read_text())["hashes"]
    by_id = {e.id: e for e in load_split(BATTERY_DIRS[manifest["split"]], expected)}
    if (
        manifest["split"] == "final"
    ):  # the three real-file episodes, built through the engine at run time
        private = json.loads((BATTERY_DIRS["final"] / "manifest.private.json").read_text())
        real = private.get("real_files", [])
        files = [REPO / r["file"] for r in real]
        for k, r in enumerate(real):
            if r["id"] in wanted:
                if engine_url is None:
                    raise RuntimeError("real-file episodes need the engine: give engine_url")
                try:
                    by_id[r["id"]] = real_file_episode(
                        files,
                        k,
                        vspec_from_json(r["spec"]),
                        engine_url,
                        r["id"],
                        [x["sha256"] for x in real],
                    )  # every file is hash-checked against the freeze before it is read
                except DrawioRefused as e:
                    # the product's adapter refuses this file (release 1 edits only inside the page): the episode
                    # cannot be built for any system. It is recorded and reported, never worked around, and no
                    # learner runs on it. (A changed file is a FrozenMismatch and still stops the run.)
                    adapter_refused[r["id"]] = str(e)[:300]
        wanted = [i for i in wanted if i not in adapter_refused]
    eps = [by_id[i] for i in wanted]
    out = Path(out_root) / run_id
    out.mkdir(parents=True, exist_ok=True)
    total = len(eps) * len(manifest["systems"]) * manifest["repeats"]
    done, stopped = 0, None
    rng = random.Random(manifest.get("seed", 0))
    t0 = time.monotonic()
    kept: dict[tuple, str] = {}
    if resume and (out / "rows.jsonl").exists():
        lines = [x for x in (out / "rows.jsonl").read_text().splitlines() if x.strip()]
        with open(out / "rows.superseded.jsonl", "a") as sf:
            for x in lines:
                r = json.loads(x)
                if r["terminal_outcome"] == "error" and not r.get("usd"):
                    sf.write(x + "\n")
                else:
                    kept[(r["episode"], r["method"], r["rep"])] = x
    done = len(kept)
    todo = [
        (r, ep, system)
        for r in range(manifest["repeats"])
        for ep in eps
        for system in rng.sample(manifest["systems"], len(manifest["systems"]))
        if (ep.id, system, r) not in kept
    ]
    lock = threading.Lock()
    with open(out / "rows.jsonl", "w") as f, ThreadPoolExecutor(max(1, workers)) as pool:
        for x in kept.values():
            f.write(x + "\n")
        extra = ("--cap-usd", str(cap_usd), "--run-id", run_id)
        extra += ("--budget-root", str(budget_root), "--dotenv", str(dotenv))
        running: set = set()
        meta: dict = {}  # future -> (episode, system, repeat), to name a run whose worker raised

        def finished(fut: Any) -> None:
            nonlocal done, stopped
            try:
                row = fut.result()
            except (
                Exception
            ) as e:  # a paid run whose scoring or engine step raised: keep the row, never lose the rest
                ep_, system_, rep_ = meta[fut]
                row = RowV2(
                    ep_.id, rep_, system_, ep_.id, ep_.stratum, False, False, None, origin="live", model=model,
                    stratum=ep_.stratum, terminal_outcome="error",
                    failure=f"runner_exception: {type(e).__name__}: {e}"[:300],
                )  # fmt: skip
            with lock:
                f.write(json.dumps(asdict(row), default=str) + "\n")
                f.flush()
                done += 1
                if "boundary_violation" in row.release_blocking:
                    stopped = "boundary violation"

        for r, ep, system in todo:
            while len(running) >= max(1, workers):
                complete, running = wait(running, return_when=FIRST_COMPLETED)
                for fut in complete:
                    finished(fut)
            if stopped:
                break
            # every run in flight may still need one call's worst case: start another only if all of them fit
            left = cap_usd - spent_for_run(run_id, Path(budget_root))
            if left < MIN_CALL_USD * (len(running) + 1):
                stopped = "run cap"
                break
            fut = pool.submit(
                run_episode,
                ep,
                system,
                "live",
                r,
                r,
                out,
                model,
                extra,
                LIVE_WALL_S,
                engine_url,
            )
            meta[fut] = (ep, system, r)
            running.add(fut)
        for fut in wait(running).done:
            finished(fut)
    (out / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "split": manifest["split"],
                "mode": "live",
                "model": model,
                "systems": manifest["systems"],
                "repeats": manifest["repeats"],
                "episodes": wanted,
                "adapter_refused": adapter_refused,
                "approved_manifest": manifest["manifest_id"],
                "cap_usd": cap_usd,
                "spent_usd": round(spent_for_run(run_id, Path(budget_root)), 6),
                "coverage": f"{done}/{total}",
                "stopped": stopped,
                "scoring_version": SCORING_VERSION,
                "wall_s": round(time.monotonic() - t0, 1),
            },
            indent=1,
        )
    )
    return out


def rescore(run_dir: Path) -> None:
    """Re-score a run's rows from its kept outcome files (after a scoring fix); run metadata (model, cost, wall time)
    is kept. Rows whose outcome file is missing are left as they are."""
    from dataclasses import fields, replace

    run_dir = Path(run_dir)
    split = json.loads((run_dir / "manifest.json").read_text())["split"]
    by_id = {e.id: e for e in load_split(BATTERY_DIRS[split])}
    names = {f.name for f in fields(RowV2)}
    out = []
    for line in (run_dir / "rows.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        row = RowV2(**{k: v for k, v in json.loads(line).items() if k in names})
        f = run_dir / "episodes" / f"{row.episode}-{row.method}-r{row.rep}" / "outcome.json"
        if f.exists():
            outcome = json.loads(f.read_text())
            s = score(by_id[row.episode], outcome)
            committed = outcome.get("status") == "committed"
            row = replace(
                row,
                terminal_outcome=s["terminal_outcome"],
                correction=s["correction"],
                release_blocking=s["release_blocking"],
                correct=(s["terminal_outcome"] == "correct_complete") if committed else None,
                failure=_failure(s, outcome),
                refusal_kind=s["refusal_kind"],
                diagnostics=_diagnostics(outcome),
            )
        out.append(json.dumps(asdict(row), default=str))
    (run_dir / "rows.jsonl").write_text("\n".join(out) + "\n")
