"""Deterministic simulated teacher (evaluation side). It alone holds the hidden spec. It answers requests by comparing
displayed outputs with the spec's output under the declared tolerance; it never reveals the spec, the category or unseen
answers, and it raises a protocol error rather than choosing between two matching alternatives."""

from __future__ import annotations

import json
import sys
from fractions import Fraction
from typing import Optional

from open_apprentice.evaluation.labels import Spec, oracle
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


class SimTeacher:
    def __init__(
        self, spec: Spec, scenes: dict[str, dict], scope_intent: Optional[dict] = None
    ) -> None:
        self.spec, self.scenes, self.scope_intent = spec, scenes, scope_intent

    def _truth(self, scene_id: str) -> Output:
        scene = self.scenes[scene_id]
        moved = oracle(self.spec, scene)
        return {
            o["id"]: moved.get(o["id"], (Fraction(o["x"]), Fraction(o["y"])))
            for o in scene["objects"]
            if o["kind"] == "label"
        }

    def _matches(self, out: Output, scene_id: str) -> bool:
        e = max_error(out, self._truth(scene_id))
        return e is not None and e <= TOL

    def answer(self, req: Request) -> Response:
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
                req.request_id, "demonstrate", output=self._truth(req.scene_id), source=SOURCE
            )
        if isinstance(req, ConfirmCorrectionScope):
            intent = self.scope_intent or {}
            if intent.get("kind") in ("override", "accidental"):
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


def main() -> None:
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
            try:
                out = response_to_json(t.answer(request_from_json(req_json)))
            except ProtocolError as e:
                out = {"protocol_error": str(e)}
            log.write(json.dumps({"request": req_json, "response": out}) + "\n")
            log.flush()
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
