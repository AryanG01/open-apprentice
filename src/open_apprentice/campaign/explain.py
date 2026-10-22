"""Plain-language explanations of the overflow question (plan 9E). The facts are measured by the engine; the model only
words them, and a deterministic check rejects any wording that adds or contradicts a fact (then a template is used)."""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field

from open_apprentice.budget import Ledger
from open_apprentice.campaign.model import call_model
from open_apprentice.campaign.run import CampaignRun
from open_apprentice.campaign.scene import role_map
from open_apprentice.providers.base import Provider, StrictModel

PROMPT = pathlib.Path(__file__).resolve().parents[3] / "prompts" / "campaign_explain.md"
MAX_CHARS = 320
SHRINK, SPLIT = "builtin_shrink_hero", "builtin_split_two_cards"
NAME = {
    "headline": "headline",
    "price": "price",
    "legal": "legal line",
    "cta": "button",
    "brand_mark": "logo",
    "background": "background",
}
WORDS = {
    "headline": ("headline",),
    "price": ("price",),
    "legal": ("legal",),
    "cta": ("button", "cta"),
    "brand_mark": ("logo", "brand mark"),
    "background": ("background",),
}
OUTCOME_WORDS = {SHRINK: "shrink", SPLIT: "split"}
NEGATIONS = ("not", "n't", "cannot", "too ")


class ExplainOut(StrictModel):
    text: str


@dataclass
class Explanation:
    text: str
    origin: str  # model | template
    problems: list[str] = field(default_factory=list)


def overflow_facts(run: CampaignRun, source: dict) -> dict:
    board = next(n["id"] for n in source["nodes"] if n["type"] == "artboard")
    roles = {nid: role for role, nid in role_map(source, board).items()}
    violations = []
    for v in run.provenance.get("base_violations", []):
        nums = [round(float(x)) for x in re.findall(r"\d+(?:\.\d+)?", str(v.get("detail", "")))]
        entry = {"role": roles.get(v["node_id"], v["node_id"]), "kind": v["kind"]}
        if v["kind"] == "text_overflow" and len(nums) >= 2:
            entry |= {"needed": nums[0], "available": nums[1]}
        violations.append(entry)
    return {"violations": violations, "outcomes": {o: p.fits for o, p in run.previews.items()}}


def template_explanation(facts: dict) -> str:
    parts = []
    for v in facts["violations"]:
        if "needed" in v:
            parts.append(
                f"the {NAME.get(v['role'], v['role'])} needs {v['needed']} px but its frame holds {v['available']} px"
            )
        else:
            parts.append(f"the {NAME.get(v['role'], v['role'])} breaks a layout limit")
    first = "; ".join(parts)
    opts = [
        f"{'Shrinking the product image' if o == SHRINK else 'Splitting across two cards'} {'fits' if fits else 'does not fit'}"
        for o, fits in facts["outcomes"].items()
    ]
    return (first[:1].upper() + first[1:] + ". " + "; ".join(opts) + ".").strip()


def check_explanation(text: str, facts: dict) -> list[str]:
    problems = []
    if len(text) > MAX_CHARS:
        problems.append(f"longer than {MAX_CHARS} characters")
    allowed = {
        n
        for v in facts["violations"]
        for n in (v.get("needed"), v.get("available"))
        if n is not None
    }
    for num in re.findall(r"\d+(?:\.\d+)?", text):
        if round(float(num)) not in allowed:
            problems.append(f"the number {num} is not in the measured facts")
    low = text.lower()
    violating = {v["role"] for v in facts["violations"]}
    for role, words in WORDS.items():
        named = any(w in low for w in words)
        if named and role not in violating:
            problems.append(f"names {role}, which did not overflow")
        if role in violating and not named:
            problems.append(f"does not mention the {role}, which overflows")
    for outcome, fits in facts["outcomes"].items():
        if fits:
            continue
        for sentence in re.split(r"[.;!?]", low):
            if OUTCOME_WORDS[outcome] in sentence and not any(n in sentence for n in NEGATIONS):
                problems.append(f"suggests {OUTCOME_WORDS[outcome]} works, but it does not fit")
    return problems


async def explain(provider: Provider | None, ledger: Ledger | None, facts: dict) -> Explanation:
    fallback = template_explanation(facts)
    if provider is None:
        return Explanation(fallback, "template")
    res = await call_model(
        provider,
        ledger,
        role="campaign_explain",
        prompt=PROMPT,
        payload=facts,
        schema=ExplainOut,
        max_tokens=600,
    )
    if res.parsed is None:
        return Explanation(fallback, "template", [res.error or "no reply"])
    problems = check_explanation(res.parsed.text, facts)
    if problems:
        return Explanation(fallback, "template", problems)
    return Explanation(res.parsed.text, "model")
