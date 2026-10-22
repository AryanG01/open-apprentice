"""One campaign run (spec 7.2, 7.5, 7.6): apply the learned layout on a scratch session, observe fit, then commit, reuse a
saved preference, or ask the owner with both built-in outcomes already applied as previews. The source scene is never
mutated: every attempt is a fresh session opened from it."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

import httpx

from open_apprentice.campaign.builtins import (
    BUILTINS,
    ORIGIN as BUILTIN_ORIGIN,
    shrink_hero,
    split_two_cards,
)
from open_apprentice.campaign.layout_rule import evaluate_layout, objects_for_rule, wrap_learned
from open_apprentice.campaign.learn import Learned
from open_apprentice.campaign.limits import fit_limits
from open_apprentice.campaign.plan import LayoutPlan, plan_from_layout
from open_apprentice.campaign.preferences import Preference, PreferenceStore, scope_key
from open_apprentice.campaign.procedures import ORIGIN as PROCEDURE_ORIGIN, apply_plan
from open_apprentice.campaign.scene import RoleError, role_map
from open_apprentice.environments.client import EngineSession

OpenSession = Callable[[dict], EngineSession]
TRANSFORMS = dict(zip(BUILTINS, (shrink_hero, split_two_cards)))


@dataclass
class Preview:
    outcome: str
    origin: str
    session_id: str
    fits: bool
    violations: list[dict]


@dataclass
class CampaignRun:
    run_id: str
    locale: str
    status: (
        str  # ready | question | applied | unchanged | needs_roles | unsupported_format | failed
    )
    source_hash: str
    result_session: Optional[str] = None
    previews: dict[str, Preview] = field(default_factory=dict)
    preference: Optional[Preference] = None
    problems: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)
    sessions: dict[str, EngineSession] = field(default_factory=dict, repr=False)
    engine_error: bool = (
        False  # the run failed because the engine itself failed (caller maps it to "busy, retry")
    )


def _hash(scene: dict) -> str:
    return hashlib.sha256(json.dumps(scene, sort_keys=True).encode()).hexdigest()


def close_run(run: CampaignRun, keep: Optional[str] = None) -> None:
    """Close the run's engine sessions, except `keep`."""
    for sid in [s for s in run.sessions if s != keep]:
        try:
            run.sessions.pop(sid).close()
        except (
            Exception
        ):  # noqa: BLE001 - best effort: one failed close must not strand the remaining sessions
            pass


def _attempt(
    run: CampaignRun,
    source: dict,
    plan: LayoutPlan,
    open_session: OpenSession,
    procedure: tuple[list, str] | None = None,
) -> tuple[str, bool, list[dict]]:
    session = open_session(source)
    run.sessions[session.session_id] = session
    apply_plan(session, plan, *(procedure or ()))
    violations: list[dict] = []
    for board in plan.artboards:
        obs = session.call("observe_fit", artboard_id=board["id"], limits=fit_limits())
        violations += obs["violations"]
    return session.session_id, not violations, violations


def start_run(
    source: dict,
    locale: str,
    learned: Learned,
    open_session: OpenSession,
    prefs: PreferenceStore,
    procedure: tuple[list, str] | None = None,
) -> CampaignRun:
    """`procedure` is (program, origin) for an accepted model-written procedure; the reference procedure otherwise."""
    run = CampaignRun(uuid.uuid4().hex, locale, "failed", _hash(source))
    run.provenance = {
        "run_id": run.run_id,
        "source_hash": run.source_hash,
        "learned_origin": learned.origin,
        "procedure_origin": procedure[1] if procedure else PROCEDURE_ORIGIN,
    }
    boards = [n["id"] for n in source["nodes"] if n["type"] == "artboard"]
    try:
        if len(boards) != 1:
            raise RoleError([f"expected one source artboard, found {len(boards)}"])
        role_map(source, boards[0])
    except RoleError as e:
        run.status, run.problems = "needs_roles", e.problems
        return run
    objs = objects_for_rule(source, boards[0])
    base_out = evaluate_layout(
        wrap_learned(learned.rule), objs, {"output_format": "9:16", "overflows": False}
    )
    if not base_out.targets:
        run.status = "unsupported_format"
        return run
    base = plan_from_layout(base_out, source, boards[0], learned.origin)
    try:
        sid, fits, violations = _attempt(run, source, base, open_session, procedure)
        if fits:
            run.status, run.result_session = "ready", sid
            close_run(run, keep=sid)
            return run
        close_run(run)
        run.provenance["base_violations"] = violations
        asked = evaluate_layout(
            wrap_learned(learned.rule), objs, {"output_format": "9:16", "overflows": True}
        ).ask
        pref = prefs.get(scope_key(locale))
        for outcome in ([pref.outcome] if pref else []) + [
            o for o in asked if not pref or o != pref.outcome
        ]:
            sid, fits, violations = _attempt(
                run, source, TRANSFORMS[outcome](base), open_session, procedure
            )
            run.previews[outcome] = Preview(outcome, BUILTIN_ORIGIN, sid, fits, violations)
            if (
                pref and outcome == pref.outcome and fits
            ):  # the saved choice still works: apply it, no question
                run.status, run.result_session, run.preference = "applied", sid, pref
                run.provenance |= {
                    "outcome_origin": BUILTIN_ORIGIN,
                    "preference_version": pref.version,
                }
                run.previews = {}
                close_run(run, keep=sid)
                return run
        run.status = "question"
        return run
    except (
        Exception
    ) as e:  # tool errors, the engine's 429 session cap, timeouts, rule/program errors: never leak a session
        close_run(run)
        run.engine_error = isinstance(e, httpx.HTTPError)
        problem = (
            "the graphics engine failed during this run; try again shortly"
            if run.engine_error
            else f"{e}"
        )
        run.status, run.problems, run.result_session, run.previews = "failed", [problem], None, {}
        return run


def answer(
    run: CampaignRun,
    choice: str,
    prefs: PreferenceStore,
    expected_version: Optional[int],
    *,
    current_source_hash: str,
) -> CampaignRun:
    """Resolve a question once: `neither` leaves the source unchanged; a fitting built-in becomes the result and the
    owner's saved preference for this language. An answer for a source that changed since the previews is refused.
    """
    if run.status != "question":
        raise ValueError(f"run {run.run_id} is {run.status}, not waiting for an answer")
    if current_source_hash != run.source_hash:
        raise ValueError("the banner changed since these previews were made; start a new run")
    if choice == "neither":
        close_run(run)
        run.status = "unchanged"
        return run
    preview = run.previews.get(choice)
    if preview is None or not preview.fits:
        raise ValueError(f"{choice} is not an applicable outcome for this banner")
    provenance = {
        **run.provenance,
        "choice": choice,
        "outcome_origin": BUILTIN_ORIGIN,
        "previews": {
            o: {"fits": p.fits, "violations": p.violations} for o, p in run.previews.items()
        },
    }
    run.preference = prefs.set(
        scope_key(run.locale), choice, provenance, expected_version
    )  # a conflict changes nothing
    run.status, run.result_session, run.provenance = "applied", preview.session_id, provenance
    close_run(run, keep=preview.session_id)
    return run
