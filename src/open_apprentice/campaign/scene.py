"""Role mapping for campaign scenes: a missing or doubled role stops the run (spec 7.1), never a guess."""

from __future__ import annotations

from open_apprentice.campaign.limits import REQUIRED_ROLES, ROLES


class RoleError(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def role_map(scene: dict, artboard_id: str) -> dict[str, str]:
    """Role -> node id for the role-bearing nodes directly inside `artboard_id`."""
    found: dict[str, list[str]] = {}
    for n in scene["nodes"]:
        if n.get("parent") == artboard_id and n.get("role"):
            found.setdefault(n["role"], []).append(n["id"])
    problems = [f"role {r} is missing" for r in REQUIRED_ROLES if r not in found]
    problems += [
        f"role {r} is claimed by more than one node: {', '.join(ids)}"
        for r, ids in found.items()
        if len(ids) > 1
    ]
    problems += [f"unknown role {r}" for r in found if r not in ROLES]
    if problems:
        raise RoleError(problems)
    return {r: ids[0] for r, ids in found.items()}
