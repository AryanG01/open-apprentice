"""The only route by which intent information reaches a learner. Three request types here (ConfirmCorrectionScope arrives
in Plan 2). Validation runs before the teacher sees a request; a malformed request is a protocol error, never an
abstention."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Optional, Protocol, Union

from open_apprentice.teaching import codec

Output = dict[str, tuple[Fraction, Fraction]]
TOL = Fraction(1, 2)
SEPARATION = Fraction(1)
PREVIEW_PURPOSES = {"learning_preview": 3, "affected_examples": 6, "revision_preview": 3}


class ProtocolError(Exception):
    pass


@dataclass(frozen=True)
class ChooseOutput:
    request_id: str
    scene_id: str
    scene_hash: str
    alternatives: tuple[tuple[str, Output], ...]


@dataclass(frozen=True)
class ConfirmPreview:
    request_id: str
    purpose: str
    items: tuple[tuple[str, str, str, Output], ...]


@dataclass(frozen=True)
class RequestDemonstration:
    request_id: str
    scene_id: str
    scene_hash: str


@dataclass(frozen=True)
class Interpretation:
    interp_id: str
    kind: str  # revise | override | accidental
    selector: Optional[str]
    summary: str
    consequences: tuple[tuple[str, str, Output], ...]


@dataclass(frozen=True)
class ConfirmCorrectionScope:
    request_id: str
    interpretations: tuple[Interpretation, ...]


Request = Union[ChooseOutput, ConfirmPreview, RequestDemonstration, ConfirmCorrectionScope]


@dataclass(frozen=True)
class Response:
    request_id: str
    kind: str
    selected: Optional[str] = None
    per_item: tuple[tuple[str, str], ...] = ()
    output: Optional[Output] = None
    source: str = "human"


class Teacher(Protocol):
    def ask(self, req: Request) -> Response: ...


def max_error(a: Output, b: Output) -> Optional[Fraction]:
    if set(a) != set(b):
        return None
    return max(
        (max(abs(a[k][0] - b[k][0]), abs(a[k][1] - b[k][1])) for k in a), default=Fraction(0)
    )


def _scene_ok(scene_id: str, scene_hash: str, registered: dict[str, str]) -> None:
    if registered.get(scene_id) != scene_hash:
        raise ProtocolError(
            f"scene {scene_id} not registered in this session or its content does not match"
        )


def validate_request(req: Request, registered: dict[str, str]) -> None:
    if isinstance(req, ChooseOutput):
        _scene_ok(req.scene_id, req.scene_hash, registered)
        if not 2 <= len(req.alternatives) <= 4:
            raise ProtocolError("ChooseOutput needs 2-4 alternatives")
        if len({a for a, _ in req.alternatives}) != len(req.alternatives):
            raise ProtocolError("duplicate alternative ids")
        outs = [o for _, o in req.alternatives]
        for i in range(len(outs)):
            for j in range(i + 1, len(outs)):
                e = max_error(outs[i], outs[j])
                if e is None:
                    raise ProtocolError("alternatives cover different labels")
                if e <= SEPARATION:
                    raise ProtocolError(
                        "alternatives are not separated by more than twice the tolerance"
                    )
    elif isinstance(req, ConfirmPreview):
        if req.purpose not in PREVIEW_PURPOSES:
            raise ProtocolError(f"unknown preview purpose {req.purpose}")
        if not 1 <= len(req.items) <= PREVIEW_PURPOSES[req.purpose]:
            raise ProtocolError(f"{req.purpose} takes 1-{PREVIEW_PURPOSES[req.purpose]} items")
        if len({i for i, *_ in req.items}) != len(req.items):
            raise ProtocolError("duplicate preview item ids")
        for _, sid, sh, _ in req.items:
            _scene_ok(sid, sh, registered)
    elif isinstance(req, RequestDemonstration):
        _scene_ok(req.scene_id, req.scene_hash, registered)
    elif isinstance(req, ConfirmCorrectionScope):
        its = req.interpretations
        if not 2 <= len(its) <= 4:
            raise ProtocolError("ConfirmCorrectionScope needs 2-4 interpretations")
        if len({i.interp_id for i in its}) != len(its):
            raise ProtocolError("duplicate interpretation ids")
        keys = [
            (i.kind, i.selector, tuple((s, tuple(sorted(o.items()))) for s, _, o in i.consequences))
            for i in its
        ]
        if len(set(keys)) != len(keys):
            raise ProtocolError("two interpretations are identical")
        for i in its:
            if i.kind not in ("revise", "override", "accidental"):
                raise ProtocolError(f"unknown interpretation kind {i.kind}")
            for sid, sh, _ in i.consequences:
                _scene_ok(sid, sh, registered)
    else:
        raise ProtocolError(f"unknown request type {type(req).__name__}")


def validate_response(req: Request, resp: Response) -> None:
    if resp.request_id != req.request_id:
        raise ProtocolError("response is for a different request")
    if isinstance(req, ChooseOutput):
        if resp.kind not in ("choose", "none", "unsure", "cancel"):
            raise ProtocolError(f"bad ChooseOutput response {resp.kind}")
        if resp.kind == "choose" and resp.selected not in {a for a, _ in req.alternatives}:
            raise ProtocolError("choice names an alternative that was not shown")
    elif isinstance(req, ConfirmPreview):
        if resp.kind != "items" or sorted(i for i, _ in resp.per_item) != sorted(
            i for i, *_ in req.items
        ):
            raise ProtocolError("preview needs exactly one verdict per item")
        if any(v not in ("approve", "reject", "unsure") for _, v in resp.per_item):
            raise ProtocolError("preview verdicts are approve/reject/unsure")
    elif isinstance(req, ConfirmCorrectionScope):
        if resp.kind not in ("select", "none", "unsure", "cancel"):
            raise ProtocolError(f"bad scope response {resp.kind}")
        if resp.kind == "select" and resp.selected not in {
            i.interp_id for i in req.interpretations
        }:
            raise ProtocolError("selection names an interpretation that was not shown")
    elif isinstance(req, RequestDemonstration):
        if resp.kind not in ("demonstrate", "decline") or (
            resp.kind == "demonstrate" and not resp.output
        ):
            raise ProtocolError("demonstration response needs an output or a decline")


def _num(v: Fraction) -> Any:
    return int(v) if v.denominator == 1 else f"{v.numerator}/{v.denominator}"


def _out_json(o: Output) -> dict:
    return {k: [_num(Fraction(x)), _num(Fraction(y))] for k, (x, y) in o.items()}


def _out_parse(d: dict) -> Output:
    return {k: (codec.frac(v[0]), codec.frac(v[1])) for k, v in d.items()}


def request_to_json(req: Request) -> dict:
    if isinstance(req, ConfirmCorrectionScope):
        return {
            "type": "ConfirmCorrectionScope",
            "request_id": req.request_id,
            "interpretations": [
                {
                    "interp_id": i.interp_id,
                    "kind": i.kind,
                    "selector": i.selector,
                    "summary": i.summary,
                    "consequences": [[s, h, _out_json(o)] for s, h, o in i.consequences],
                }
                for i in req.interpretations
            ],
        }
    if isinstance(req, ChooseOutput):
        return {
            "type": "ChooseOutput",
            "request_id": req.request_id,
            "scene_id": req.scene_id,
            "scene_hash": req.scene_hash,
            "alternatives": [[a, _out_json(o)] for a, o in req.alternatives],
        }
    if isinstance(req, ConfirmPreview):
        return {
            "type": "ConfirmPreview",
            "request_id": req.request_id,
            "purpose": req.purpose,
            "items": [[i, s, h, _out_json(o)] for i, s, h, o in req.items],
        }
    return {
        "type": "RequestDemonstration",
        "request_id": req.request_id,
        "scene_id": req.scene_id,
        "scene_hash": req.scene_hash,
    }


def request_from_json(d: dict) -> Request:
    if d["type"] == "ChooseOutput":
        return ChooseOutput(
            d["request_id"],
            d["scene_id"],
            d["scene_hash"],
            tuple((a, _out_parse(o)) for a, o in d["alternatives"]),
        )
    if d["type"] == "ConfirmPreview":
        return ConfirmPreview(
            d["request_id"],
            d["purpose"],
            tuple((i, s, h, _out_parse(o)) for i, s, h, o in d["items"]),
        )
    if d["type"] == "ConfirmCorrectionScope":
        return ConfirmCorrectionScope(
            d["request_id"],
            tuple(
                Interpretation(
                    i["interp_id"],
                    i["kind"],
                    i["selector"],
                    i["summary"],
                    tuple((s, h, _out_parse(o)) for s, h, o in i["consequences"]),
                )
                for i in d["interpretations"]
            ),
        )
    if d["type"] == "RequestDemonstration":
        return RequestDemonstration(d["request_id"], d["scene_id"], d["scene_hash"])
    raise ProtocolError(f"unknown request type {d['type']}")


def response_to_json(r: Response) -> dict:
    return {
        "request_id": r.request_id,
        "kind": r.kind,
        "selected": r.selected,
        "per_item": [list(p) for p in r.per_item],
        "output": _out_json(r.output) if r.output else None,
        "source": r.source,
    }


def response_from_json(d: dict) -> Response:
    return Response(
        d["request_id"],
        d["kind"],
        d.get("selected"),
        tuple((p[0], p[1]) for p in d.get("per_item", [])),
        _out_parse(d["output"]) if d.get("output") else None,
        d.get("source", "human"),
    )


class SubprocessTeacher:
    """Talks to a teacher process over JSON lines (one request per line, one response per line)."""

    def __init__(self, argv: list[str]) -> None:
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    def ask(self, req: Request) -> Response:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(request_to_json(req)) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise ProtocolError("teacher process closed")
        d = json.loads(line)
        if "protocol_error" in d:
            raise ProtocolError(d["protocol_error"])
        return response_from_json(d)

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.wait(timeout=10)
