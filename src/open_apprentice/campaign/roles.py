"""Role proposals for banners that arrive without role tags (plan 9E). Nemotron proposes, a deterministic check rejects
impossible mappings, a heuristic is the fallback, and the owner confirms before any run."""

from __future__ import annotations

import copy
import pathlib
import re
from dataclasses import dataclass, field

from open_apprentice.budget import Ledger
from open_apprentice.campaign.limits import ROLES
from open_apprentice.campaign.model import call_model
from open_apprentice.providers.base import Provider, StrictModel

PROMPT = pathlib.Path(__file__).resolve().parents[3] / "prompts" / "campaign_roles.md"


class RolesOut(StrictModel):
    roles: dict[str, str]


@dataclass
class RoleProposal:
    mapping: dict[str, str]  # node id -> role
    origin: str  # model | heuristic
    problems: list[str] = field(
        default_factory=list
    )  # why a model proposal was rejected, if it was


def _layers(scene: dict, artboard: str) -> list[dict]:
    return [n for n in scene["nodes"] if n.get("parent") == artboard]


def _children(scene: dict, nid: str) -> list[dict]:
    return [n for n in scene["nodes"] if n.get("parent") == nid]


def role_candidates(scene: dict, artboard: str) -> list[dict]:
    """Exactly what the model is shown: no roles, no gold, text cut to 200 characters."""
    out = []
    for n in _layers(scene, artboard):
        c = {
            "id": n["id"],
            "type": n["type"],
            "box": [n["x"], n["y"], n.get("width"), n.get("height")],
        }
        if n["type"] == "text":
            c |= {"text": n["text"][:200], "fontSize": n["fontSize"]}
        if n["type"] == "image":
            c["asset"] = n["asset"]
        if n["type"] == "group":
            c["children"] = sorted(k["type"] for k in _children(scene, n["id"]))
        out.append(c)
    return out


def check_role_mapping(scene: dict, artboard: str, mapping: dict[str, str]) -> list[str]:
    layers = {n["id"]: n for n in _layers(scene, artboard)}
    board = next((n for n in scene["nodes"] if n["id"] == artboard), None)
    problems = [f"{nid} is not a layer of the banner" for nid in mapping if nid not in layers]
    by_role: dict[str, list[str]] = {}
    for nid, role in mapping.items():
        by_role.setdefault(role, []).append(nid)
    problems += [f"unknown role {r}" for r in by_role if r not in ROLES]
    problems += [f"role {r} is missing" for r in ROLES if r not in by_role]
    problems += [
        f"role {r} is given to more than one layer" for r, ids in by_role.items() if len(ids) > 1
    ]
    if problems:
        return problems
    n = {r: layers[ids[0]] for r, ids in by_role.items()}
    bg = n["background"]
    if (
        bg["type"] != "rect"
        or not board
        or bg["width"] * bg["height"] < 0.9 * board["width"] * board["height"]
    ):
        problems.append("background must be a rect covering the banner")
    for r in ("brand_mark", "product_image"):
        if n[r]["type"] != "image":
            problems.append(f"{r} must be an image")
    for r in ("headline", "price", "legal"):
        if n[r]["type"] != "text":
            problems.append(f"{r} must be text")
    if n["price"]["type"] == "text" and not re.search(r"\d", n["price"]["text"]):
        problems.append("price must contain a number")
    kids = sorted(k["type"] for k in _children(scene, n["cta"]["id"]))
    if n["cta"]["type"] != "group" or kids != ["shape", "text"]:
        problems.append("cta must be a group holding a shape and a text")
    return problems


def heuristic_roles(scene: dict, artboard: str) -> dict[str, str]:
    """Deterministic baseline: biggest rect is the background, biggest image the product, the other image the logo, the
    group the CTA; text by font size (largest headline, middle price, smallest legal)."""
    layers = _layers(scene, artboard)
    area = lambda x: (x.get("width") or 0) * (x.get("height") or 0)
    out: dict[str, str] = {}
    rects = sorted((x for x in layers if x["type"] == "rect"), key=area, reverse=True)
    images = sorted((x for x in layers if x["type"] == "image"), key=area, reverse=True)
    texts = sorted(
        (x for x in layers if x["type"] == "text"), key=lambda x: (-x["fontSize"], x["y"])
    )
    groups = [x for x in layers if x["type"] == "group"]
    for role, pick in (
        ("background", rects[:1]),
        ("product_image", images[:1]),
        ("brand_mark", images[1:2]),
        ("cta", groups[:1]),
    ):
        out.update({x["id"]: role for x in pick})
    for role, x in zip(("headline", "price", "legal"), texts):
        out[x["id"]] = role
    return out


async def propose_roles(
    provider: Provider | None, ledger: Ledger | None, scene: dict, artboard: str
) -> RoleProposal:
    if provider is None:
        return RoleProposal(heuristic_roles(scene, artboard), "heuristic")
    res = await call_model(
        provider, ledger, role="campaign_roles", prompt=PROMPT,
        payload={"layers": role_candidates(scene, artboard)}, schema=RolesOut, max_tokens=1500,
    )  # fmt: skip
    if res.parsed is None:
        return RoleProposal(
            heuristic_roles(scene, artboard), "heuristic", [res.error or "no reply"]
        )
    problems = check_role_mapping(scene, artboard, res.parsed.roles)
    if problems:
        return RoleProposal(heuristic_roles(scene, artboard), "heuristic", problems)
    return RoleProposal(dict(res.parsed.roles), "model")


def apply_roles(scene: dict, artboard: str, mapping: dict[str, str]) -> dict:
    """A tagged copy; the caller applies it only after the owner confirmed the mapping."""
    out = copy.deepcopy(scene)
    for n in out["nodes"]:
        if n.get("parent") == artboard and n["id"] in mapping:
            n["role"] = mapping[n["id"]]
    return out
