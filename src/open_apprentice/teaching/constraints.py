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
    preview_approved: dict[str, Output] = field(default_factory=dict)
    rejected: dict[str, list[Output]] = field(default_factory=dict)
    items: list = field(default_factory=list)  # list[EvidenceItem], ids "<event_id>:<k>"

    @property
    def batch(self) -> list[str]:
        return [s for s, r in self.roles.items() if r == "batch"]


def _positive(e: Evidence, sid: str, out: Output, source: str, item_id: str) -> None:
    from open_apprentice.teaching.evidence import (
        EvidenceItem,
    )  # local: evidence imports this module

    sc = e.scenes[sid]
    e.positives.append(Constraint("positive", sc, to_state(apply_output(sc, out)), source=source))
    e.approved[sid] = out
    e.items.append(EvidenceItem(item_id, "full", sid, sc, output=out, source=source))


def _excludes(e: Evidence, sid: str, outs: list[Output], source: str, item_id: str) -> None:
    from open_apprentice.teaching.evidence import EvidenceItem

    sc = e.scenes[sid]
    excl = tuple(to_state(apply_output(sc, o)) for o in outs)
    e.negatives.append(Constraint("excludes", sc, excluded=excl, source=source))
    e.rejected.setdefault(sid, []).extend(outs)
    e.items.append(EvidenceItem(item_id, "excludes", sid, sc, excluded=tuple(outs), source=source))


TEACHER_ORIGINS = frozenset({"human", "simulator"})


def derive(events: list[Event]) -> Evidence:
    e = Evidence()
    requests: dict[str, Request] = {}
    responded: set[str] = set()
    for ev in events:
        p = ev.payload
        if (
            ev.type in ("DemonstrationRecorded", "ResponseRecorded")
            and ev.origin not in TEACHER_ORIGINS
        ):
            continue  # only the teacher creates intent
        if ev.type == "SceneRegistered":
            e.scenes[p["scene_id"]] = scene_from_payload(p["scene"])
            e.scene_hashes[p["scene_id"]] = p["scene_hash"]
            e.roles[p["scene_id"]] = p["role"]
        elif ev.type == "DemonstrationRecorded":
            _positive(
                e, p["scene_id"], _parse_out(p["output"]), "demonstration", f"{ev.event_id}:0"
            )
        elif ev.type == "RequestIssued":
            req = request_from_json(p["request"])
            requests[req.request_id] = req
        elif ev.type == "ResponseRecorded":
            r = response_from_json(p["response"])
            if r.request_id in responded:
                continue  # one request, one response: later duplicates carry no evidence
            responded.add(r.request_id)
            req = requests.get(r.request_id)
            if isinstance(req, ChooseOutput):
                if r.kind == "choose" and r.selected is not None:
                    _positive(
                        e,
                        req.scene_id,
                        dict(req.alternatives)[r.selected],
                        "answer",
                        f"{ev.event_id}:0",
                    )
                elif r.kind == "none":
                    shown = [o for _, o in req.alternatives]
                    _excludes(e, req.scene_id, shown, "neither", f"{ev.event_id}:0")
            elif isinstance(req, ConfirmPreview):
                verdicts = dict(r.per_item)
                for k, (item_id, sid, _, out) in enumerate(req.items):
                    if verdicts.get(item_id) == "approve":
                        _positive(e, sid, out, "preview", f"{ev.event_id}:{k}")
                        e.preview_approved[sid] = out
                    elif verdicts.get(item_id) == "reject":
                        _excludes(e, sid, [out], "preview_reject", f"{ev.event_id}:{k}")
            elif isinstance(req, RequestDemonstration) and r.kind == "demonstrate" and r.output:
                _positive(e, req.scene_id, r.output, "requested_demonstration", f"{ev.event_id}:0")
    return e
