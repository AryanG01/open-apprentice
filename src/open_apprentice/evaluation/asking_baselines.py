"""Scripted policies for the calibrated-asking environment. No model. They show that the reward components SEPARATE different
behaviours, which is what makes the environment informative; they are not contenders and make no claim about language models.

  never_ask       commits the simplest rule of the declared grammar that fits the demonstration
  always_ask      always spends every question, then commits the first rule consistent with the answers
  calibrated      asks only while more than one behaviourally distinct rule still fits, choosing the input that splits them most
  always_abstain  never commits
"""

from __future__ import annotations

from typing import Callable

from open_apprentice.concepts.rules import RuleError, evaluate_rule
from open_apprentice.evaluation.asking_env import (
    MAX_ASKS,
    AskingEnv,
    _badge_scene,
    _pub,
    _spacing_scene,
)

BADGE_PROBES = [[60], [100], [150], [200], [300], [400], [500]]
SPACING_PROBES = [[60, 60, 60], [120, 80, 200], [200, 200, 200], [40, 300, 40], [100, 200, 100]]


def _probe_scene(env: AskingEnv, widths: list[int]) -> dict:
    return _badge_scene(widths[0], env._demo) if env.kind == "badge" else _spacing_scene(widths)


def _outcome(rule: list, scene: dict):
    try:
        return _pub(evaluate_rule(rule, scene["objects"], scene["canvas"]))
    except RuleError:
        return None


def _probes(env: AskingEnv) -> list[list[int]]:
    return BADGE_PROBES if env.kind == "badge" else SPACING_PROBES


def never_ask(env: AskingEnv) -> None:
    cands = env.fitting_candidates()
    env.commit(cands[0].rule) if cands else env.abstain()


def _consistent(cands: list, env: AskingEnv, widths: list[int], answer: dict) -> list:
    scene = _probe_scene(env, widths)
    return [c for c in cands if _outcome(c.rule, scene) == answer["after"]]


def always_ask(env: AskingEnv) -> None:
    cands = env.fitting_candidates()
    for widths in _probes(env)[:MAX_ASKS]:
        ans = env.ask({"card_widths": widths})
        if ans["ok"]:
            cands = _consistent(cands, env, widths, ans) or cands
    env.commit(cands[0].rule) if cands else env.abstain()


def calibrated(env: AskingEnv) -> None:
    cands = env.fitting_candidates()
    while len(cands) > 1 and env.asks_used < MAX_ASKS:
        best, best_n = None, 1
        for widths in _probes(env):
            scene = _probe_scene(env, widths)
            n = len({repr(_outcome(c.rule, scene)) for c in cands})
            if n > best_n:
                best, best_n = widths, n
        if (
            best is None
        ):  # no probe separates the remaining rules: they are equivalent on everything we can ask
            break
        ans = env.ask({"card_widths": best})
        if not ans["ok"]:
            break
        cands = _consistent(cands, env, best, ans) or cands
    env.commit(cands[0].rule) if cands else env.abstain()


def always_abstain(env: AskingEnv) -> None:
    env.abstain()


POLICIES: dict[str, Callable[[AskingEnv], None]] = {
    "never_ask": never_ask,
    "always_ask": always_ask,
    "calibrated": calibrated,
    "always_abstain": always_abstain,
}


def run_policy(name: str, split: str, seed: int, index: int, kind: str) -> dict:
    env = AskingEnv(split, seed, index, kind)
    POLICIES[name](env)
    return {
        "policy": name,
        "split": split,
        "seed": seed,
        "index": index,
        "kind": kind,
        **env.score(),
    }
