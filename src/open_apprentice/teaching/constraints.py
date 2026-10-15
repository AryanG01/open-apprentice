"""Intent constraints are DERIVED from committed human/simulator events; they are never stored separately. Mechanical
feedback never creates intent constraints. Semantics: spec section 3.5."""

from __future__ import annotations

from dataclasses import dataclass, field

from open_apprentice.concepts.hypotheses import Constraint
from open_apprentice.concepts.label_teaching import to_state
from open_apprentice.teaching import codec
from open_apprentice.teaching.events import Event
from open_apprentice.teaching.teacher import (
    ChooseOutput,
    ConfirmPreview,
    Output,
    Request,
    RequestDemonstration,
    request_from_json,
    response_from_json,
)


def scene_from_payload(d: dict) -> dict:
    objs = [{**o, **{f: codec.frac(o[f]) for f in ("x", "y", "w", "h")}} for o in d["objects"]]
    return {"objects": objs, "canvas": {k: codec.frac(v) for k, v in d["canvas"].items()}}


def apply_output(scene: dict, out: Output) -> dict:
    objs = [
        dict(o, x=out[o["id"]][0], y=out[o["id"]][1]) if o["id"] in out else dict(o)
        for o in scene["objects"]
    ]
    return {"objects": objs, "canvas": scene["canvas"]}


def _parse_out(d: dict) -> Output:
    return {k: (codec.frac(v[0]), codec.frac(v[1])) for k, v in d.items()}


@dataclass
class Evidence:
    scenes: dict[str, dict] = field(default_factory=dict)
    scene_hashes: dict[str, str] = field(default_factory=dict)
    roles: dict[str, str] = field(default_factory=dict)
    positives: list[Constraint] = field(default_factory=list)
    negatives: list[Constraint] = field(default_factory=list)
    approved: dict[str, Output] = field(default_factory=dict)
    rejected: dict[str, list[Output]] = field(default_factory=dict)

    @property
    def batch(self) -> list[str]:
        return [s for s, r in self.roles.items() if r == "batch"]


def _positive(e: Evidence, sid: str, out: Output, source: str) -> None:
    sc = e.scenes[sid]
    e.positives.append(Constraint("positive", sc, to_state(apply_output(sc, out)), source=source))
    e.approved[sid] = out


def derive(events: list[Event]) -> Evidence:
    e = Evidence()
    requests: dict[str, Request] = {}
    for ev in events:
        p = ev.payload
        if ev.type == "SceneRegistered":
            e.scenes[p["scene_id"]] = scene_from_payload(p["scene"])
            e.scene_hashes[p["scene_id"]] = p["scene_hash"]
            e.roles[p["scene_id"]] = p["role"]
        elif ev.type == "DemonstrationRecorded":
            _positive(e, p["scene_id"], _parse_out(p["output"]), "demonstration")
        elif ev.type == "RequestIssued":
            req = request_from_json(p["request"])
            requests[req.request_id] = req
        elif ev.type == "ResponseRecorded":
            r = response_from_json(p["response"])
            req = requests.get(r.request_id)
            if isinstance(req, ChooseOutput):
                sc = e.scenes[req.scene_id]
                if r.kind == "choose" and r.selected is not None:
                    _positive(e, req.scene_id, dict(req.alternatives)[r.selected], "answer")
                elif r.kind == "none":
                    excl = tuple(to_state(apply_output(sc, o)) for _, o in req.alternatives)
                    e.negatives.append(Constraint("excludes", sc, excluded=excl, source="neither"))
                    e.rejected.setdefault(req.scene_id, []).extend(o for _, o in req.alternatives)
            elif isinstance(req, ConfirmPreview):
                verdicts = dict(r.per_item)
                for item_id, sid, _, out in req.items:
                    if verdicts.get(item_id) == "approve":
                        _positive(e, sid, out, "preview")
                    elif verdicts.get(item_id) == "reject":
                        sc = e.scenes[sid]
                        bad = (to_state(apply_output(sc, out)),)
                        e.negatives.append(
                            Constraint("excludes", sc, excluded=bad, source="preview_reject")
                        )
                        e.rejected.setdefault(sid, []).append(out)
            elif isinstance(req, RequestDemonstration) and r.kind == "demonstrate" and r.output:
                _positive(e, req.scene_id, r.output, "requested_demonstration")
    return e
