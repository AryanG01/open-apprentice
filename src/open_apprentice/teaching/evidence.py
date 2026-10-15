"""Identified evidence items. A version stores its evidence as a list of these, so a correction can rebuild, supersede and
replace individual pieces of evidence by id."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from open_apprentice.teaching.constraints import scene_from_payload
from open_apprentice.teaching.step import run_output
from open_apprentice.teaching.teacher import TOL, Output, _out_json, _out_parse, max_error


@dataclass(frozen=True)
class EvidenceItem:
    id: str
    kind: str  # full | masked | excludes
    scene_id: str
    scene: dict
    output: Optional[Output] = None
    mask: tuple[str, ...] = ()
    excluded: tuple[Output, ...] = ()
    source: str = ""


def item_fits(rule: list, item: EvidenceItem) -> tuple[bool, str]:
    out = run_output(rule, item.scene)
    if out is None:
        return False, f"{item.id}: the program fails to run on {item.scene_id}"
    if item.kind == "full":
        e = max_error(out, item.output or {})
        ok = e is not None and e <= TOL
        return ok, "" if ok else f"{item.id}: differs from the approved output on {item.scene_id}"
    if item.kind == "masked":
        sub = {k: out[k] for k in item.mask if k in out}
        e = max_error(sub, item.output or {})
        ok = e is not None and e <= TOL
        return ok, "" if ok else f"{item.id}: corrected labels differ on {item.scene_id}"
    for bad in item.excluded:
        e = max_error(out, bad)
        if e is not None and e <= TOL:
            return False, f"{item.id}: reproduces a rejected output on {item.scene_id}"
    return True, ""


def item_to_json(item: EvidenceItem) -> dict:
    return {
        "id": item.id,
        "kind": item.kind,
        "scene_id": item.scene_id,
        "scene": item.scene,
        "output": _out_json(item.output) if item.output is not None else None,
        "mask": list(item.mask),
        "excluded": [_out_json(o) for o in item.excluded],
        "source": item.source,
    }


def item_from_json(d: dict) -> EvidenceItem:
    from open_apprentice.teaching import codec

    scene = codec.loads(codec.dumps(d["scene"]))  # accept Fraction-bearing or JSON scenes alike
    return EvidenceItem(
        d["id"],
        d["kind"],
        d["scene_id"],
        scene_from_payload(scene),
        _out_parse(d["output"]) if d.get("output") is not None else None,
        tuple(d.get("mask", [])),
        tuple(_out_parse(o) for o in d.get("excluded", [])),
        d.get("source", ""),
    )
