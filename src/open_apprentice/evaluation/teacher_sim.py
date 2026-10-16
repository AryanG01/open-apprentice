"""Deterministic simulated teacher (evaluation side). It alone holds the hidden spec. It answers requests by comparing
displayed outputs with the spec's output under the declared tolerance; it never reveals the spec, the category or unseen
answers, and it raises a protocol error rather than choosing between two matching alternatives.

Battery episodes (Plan 5): `teacher_for(ep)` / `main(private_episode.json, log.jsonl)` load the hidden behaviour (a VSpec),
the correction script and every scene of the episode. Once a correction is under way (a scope question or a correction
preview has been asked) outputs are judged against the corrected behaviour. A generated probe is unknown to this process
until the learner displays it: the request line then carries the scene, which is accepted only if it hashes to the
request's scene_hash."""

from __future__ import annotations

import json
import sys
from fractions import Fraction
from typing import Any, Optional, Union

from open_apprentice.evaluation.labels import Spec
from open_apprentice.evaluation.specs_v2 import VSpec, oracle_v
from open_apprentice.teaching import codec
from open_apprentice.teaching.constraints import scene_from_payload
from open_apprentice.teaching.scope import members
from open_apprentice.teaching.teacher import (
    TOL,
    ChooseOutput,
    ConfirmCorrectionScope,
    ConfirmPreview,
    Interpretation,
    Output,
    ProtocolError,
    Request,
    RequestDemonstration,
    Response,
    max_error,
    request_from_json,
    response_to_json,
)

SOURCE = "deterministic_simulator"
CORRECTION_PURPOSES = ("affected_examples", "revision_preview")


def _v(spec: Union[Spec, VSpec]) -> VSpec:
    return spec if isinstance(spec, VSpec) else VSpec("catalogue", (spec,))


class SimTeacher:
    def __init__(
        self,
        spec: Union[Spec, VSpec],
        scenes: dict[str, dict],
        scope_intent: Optional[dict] = None,
        demo_spec: Optional[VSpec] = None,
    ) -> None:
        self.spec, self.scenes, self.scope_intent = _v(spec), dict(scenes), scope_intent
        self.demo_spec = (
            demo_spec  # inconsistent episodes: demonstrations follow the conflicting script
        )
        self.correcting = False

    def _active(self) -> VSpec:
        new = (self.scope_intent or {}).get("new_spec")
        return _v(new) if self.correcting and new is not None else self.spec

    def _truth(self, scene_id: str, spec: Optional[VSpec] = None) -> Output:
        if scene_id not in self.scenes:
            raise ProtocolError(f"scene {scene_id} was never shown to the teacher")
        scene = self.scenes[scene_id]
        moved = oracle_v(spec or self._active(), scene)
        return {
            o["id"]: moved.get(o["id"], (Fraction(o["x"]), Fraction(o["y"])))
            for o in scene["objects"]
            if o["kind"] == "label"
        }

    def _matches(self, out: Output, scene_id: str) -> bool:
        e = max_error(out, self._truth(scene_id))
        return e is not None and e <= TOL

    def show(self, scene_id: str, scene_hash: str, payload: dict) -> None:
        """A scene displayed with a request (a generated probe). Accepted only if it hashes to what the request names."""
        scene = scene_from_payload(payload)
        if codec.digest(scene) != scene_hash:
            raise ProtocolError(f"displayed scene {scene_id} does not match its hash")
        if scene_id in self.scenes and codec.digest(self.scenes[scene_id]) != scene_hash:
            raise ProtocolError(f"scene {scene_id} is already registered with other content")
        self.scenes[scene_id] = scene

    def answer(self, req: Request) -> Response:
        if isinstance(req, ConfirmCorrectionScope) or (
            isinstance(req, ConfirmPreview) and req.purpose in CORRECTION_PURPOSES
        ):
            self.correcting = True
        if isinstance(req, ChooseOutput):
            hits = [a for a, out in req.alternatives if self._matches(out, req.scene_id)]
            if len(hits) > 1:
                raise ProtocolError("more than one alternative matches the intended output")
            if hits:
                return Response(req.request_id, "choose", selected=hits[0], source=SOURCE)
            return Response(req.request_id, "none", source=SOURCE)
        if isinstance(req, ConfirmPreview):
            verdicts = tuple(
                (i, "approve" if self._matches(out, sid) else "reject")
                for i, sid, _, out in req.items
            )
            return Response(req.request_id, "items", per_item=verdicts, source=SOURCE)
        if isinstance(req, RequestDemonstration):
            return Response(
                req.request_id,
                "demonstrate",
                output=self._truth(req.scene_id, self.demo_spec),
                source=SOURCE,
            )
        if isinstance(req, ConfirmCorrectionScope):
            intent = self.scope_intent or {}
            if intent.get("kind") == "conflict":
                hits = []  # the teacher authorizes no scope: the edit stays a conflict
            elif intent.get("kind") in ("override", "accidental"):
                hits = [i.interp_id for i in req.interpretations if i.kind == intent["kind"]]
            else:
                hits = [
                    i.interp_id
                    for i in req.interpretations
                    if i.kind == "revise" and self._means(i, intent)
                ]
            if len(hits) > 1:
                raise ProtocolError("more than one interpretation matches the intended change")
            if hits:
                return Response(req.request_id, "select", selected=hits[0], source=SOURCE)
            return Response(req.request_id, "none", source=SOURCE)
        raise ProtocolError(f"unsupported request {type(req).__name__}")

    def ask(self, req: Request) -> Response:
        """The Teacher protocol: lets the in-process simulator stand in where a subprocess teacher would be used."""
        return self.answer(req)

    def _means(self, interp: Interpretation, intent: dict) -> bool:
        """Bounded meaning check: same members as the intended selector on every diagnostic scene, and every shown
        consequence matches the intended new behaviour within tolerance."""
        if not intent or interp.selector is None:
            return False
        for sid in intent["diagnostic_scenes"]:
            if members(interp.selector, self.scenes[sid]) != members(
                intent["selector"], self.scenes[sid]
            ):
                return False
        new = SimTeacher(intent["new_spec"], self.scenes)
        return all(new._matches(out, sid) for sid, _, out in interp.consequences)


def teacher_for(ep: Any) -> SimTeacher:
    """The simulated teacher of one battery episode (`battery_v2.Episode`)."""
    from open_apprentice.evaluation.battery_v2 import scene_ids, vspec_from_json

    c = ep.correction
    intent = None
    if c is not None:
        intent = {
            "kind": c["kind"],
            "selector": c["selector"],
            "new_spec": c["spec"],
            "diagnostic_scenes": [f"x{i}" for i in range(len(c["diagnostic_scenes"]))],
        }
    conflict = ep.meta.get("conflict_spec")
    demo = vspec_from_json(conflict) if conflict else None
    return SimTeacher(ep.spec, scene_ids(ep), scope_intent=intent, demo_spec=demo)


def handle(t: SimTeacher, req_json: dict) -> dict:
    """One JSON line in, one out. Protocol errors are answered, never raised."""
    try:
        if "scene" in req_json:
            t.show(req_json["scene_id"], req_json["scene_hash"], req_json["scene"])
        return response_to_json(t.answer(request_from_json(req_json)))
    except ProtocolError as e:
        return {"protocol_error": str(e)}


def main() -> None:
    if len(sys.argv) == 3:  # battery episode: private episode file, log
        from open_apprentice.evaluation.battery_v2 import episode_from_json

        ep_path, log_path = sys.argv[1:3]
        with open(ep_path, "rb") as fb:
            t = teacher_for(episode_from_json(codec.loads(fb.read())))
    else:
        spec_path, scenes_path, log_path = sys.argv[1:4]
        with open(spec_path) as f:
            s = json.load(f)
        spec = Spec(s["primary"], s["fallback"], s["scope"], Fraction(s["gap"]))
        with open(scenes_path) as f:
            scenes = {k: scene_from_payload(v) for k, v in json.load(f).items()}
        t = SimTeacher(spec, scenes)
    with open(log_path, "a") as log:
        for line in sys.stdin:
            req_json = json.loads(line)
            out = handle(t, req_json)
            log.write(json.dumps({"request": req_json, "response": out}) + "\n")
            log.flush()
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
