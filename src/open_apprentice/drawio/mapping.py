"""Label → node mapping sidecar, bound to one document hash and page (spec 6). The system only proposes; a teacher event
confirms. Any edit clears the confirmation, and the digest changes so the caller raises intent_revision."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Optional

from open_apprentice.drawio.classify import Classified
from open_apprentice.drawio.parse import DrawioRefused
from open_apprentice.drawio.render import Box, Rendered


@dataclass(frozen=True)
class Mapping:
    doc_hash: str
    page_id: str
    labels: dict[str, dict[str, str]]  # cell -> {"node_id", "role"}
    proposed: frozenset[str]  # entries that are still the system's proposal
    confirmed_by_event: Optional[str]


def _gap(a: Box, b: Box) -> Fraction:
    dx = max(Fraction(0), a.x - (b.x + b.w), b.x - (a.x + a.w))
    dy = max(Fraction(0), a.y - (b.y + b.h), b.y - (a.y + a.h))
    return dx * dx + dy * dy


def propose(c: Classified, r: Rendered, doc_hash: str) -> Mapping:
    nodes = sorted(cid for cid in c.fixed if cid in r.nodes and cid not in c.reasons)
    labels = {}
    for cid in c.movable:
        if cid in r.labels and nodes:
            box = r.labels[cid][0]
            best = min(nodes, key=lambda n: (_gap(box, r.nodes[n][0]), n))
            labels[cid] = {"node_id": best, "role": "note"}
    return Mapping(doc_hash, c.page.id, labels, frozenset(labels), None)


def edit(
    m: Mapping,
    cell_id: str,
    *,
    node_id: Optional[str] = None,
    role: Optional[str] = None,
    nodes: frozenset[str],
) -> Mapping:
    if cell_id not in m.labels:
        raise ValueError(f"{cell_id!r} is not a mapped label")
    entry = dict(m.labels[cell_id])
    if node_id is not None:
        if node_id not in nodes:
            raise ValueError(f"{node_id!r} is not a node on this page")
        entry["node_id"] = node_id
    if role is not None:
        entry["role"] = role.strip().lower()
    return replace(
        m,
        labels={**m.labels, cell_id: entry},
        proposed=m.proposed - {cell_id},
        confirmed_by_event=None,
    )


def confirm(m: Mapping, event_id: str) -> Mapping:
    return replace(m, proposed=frozenset(), confirmed_by_event=event_id)


def to_json(m: Mapping) -> dict:
    return {
        "doc_hash": m.doc_hash,
        "page_id": m.page_id,
        "labels": m.labels,
        "proposed": sorted(m.proposed),
        "confirmed_by_event": m.confirmed_by_event,
    }


def from_json(d: dict) -> Mapping:
    return Mapping(
        d["doc_hash"],
        d["page_id"],
        {k: dict(v) for k, v in d["labels"].items()},
        frozenset(d["proposed"]),
        d["confirmed_by_event"],
    )


def digest(m: Mapping) -> str:
    body = json.dumps(
        {"doc_hash": m.doc_hash, "page_id": m.page_id, "labels": m.labels},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(body.encode()).hexdigest()


def as_scene_mapping(
    m: Mapping, doc_hash: str, page_id: str, movable: tuple[str, ...]
) -> dict[str, tuple[str, str]]:
    if (m.doc_hash, m.page_id) != (doc_hash, page_id):
        raise DrawioRefused("this mapping belongs to another document or page")
    if m.confirmed_by_event is None:
        raise DrawioRefused("the label mapping has not been confirmed")
    missing = [cid for cid in movable if cid not in m.labels]
    if missing:
        raise DrawioRefused(f"labels without a mapping: {missing}")
    return {cid: (v["node_id"], v["role"]) for cid, v in m.labels.items()}
