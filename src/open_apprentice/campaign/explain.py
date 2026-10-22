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


CLAUSE = re.compile(r"[.;:!?,\u2014\u2013]|\bbut\b|\bwhile\b|\bwhereas\b")
NOT_FIT = (
    "does not fit",
    "doesn't fit",
    "not enough",
    "cannot",
    "can't",
    "won't fit",
    "would not fit",
    "still overflow",
    "does not work",
    "doesn't work",
    "is not enough",
    "too ",
)
FIT = ("fits", "fit ", "works", "resolves", "solves")
NEGATION = re.compile(r"\b(not|no|never|cannot|can't|won't|doesn't|isn't|wouldn't)\b")
BANNED = re.compile(
    r"\(true\)|\(false\)|shrink_hero|split_two_cards|builtin_|https?://|www\.|@|\b[\w-]+\.(?:com|net|org|io|example|dev|app)\b"
)


def check_explanation(text: str, facts: dict) -> list[str]:
    """Rejects any wording that adds, drops, swaps or contradicts a measured fact."""
    problems = []
    low = text.lower()
    if len(text) > MAX_CHARS:
        problems.append(f"longer than {MAX_CHARS} characters")
    if BANNED.search(low):
        problems.append("contains raw ids, true/false values or a link")
    allowed = {
        n
        for v in facts["violations"]
        for n in (v.get("needed"), v.get("available"))
        if n is not None
    }
    for num in re.findall(r"\d+(?:\.\d+)?", text):
        if round(float(num)) not in allowed:
            problems.append(f"the number {num} is not in the measured facts")
    violating = {v["role"] for v in facts["violations"]}
    for role, words in WORDS.items():
        hits = [m.start() for w in words for m in re.finditer(rf"\b{re.escape(w)}\b", low)]
        if hits and role not in violating:
            problems.append(f"names {role}, which did not overflow")
        if role in violating and not hits:
            problems.append(f"does not mention the {role}, which overflows")
    for v in facts[
        "violations"
    ]:  # each role's numbers in order: what it needs, then what its frame holds
        if "needed" not in v:
            continue
        starts = [
            m.start()
            for w in WORDS.get(v["role"], (v["role"],))
            for m in re.finditer(rf"\b{re.escape(w)}\b", low)
        ]
        ok = False
        for r in starts:
            n = low.find(str(v["needed"]), r)
            if n >= 0 and low.find(str(v["available"]), n + len(str(v["needed"]))) >= 0:
                ok = True
        if starts and not ok:
            problems.append(
                f"the {v['role']}'s numbers are missing or out of order (needs {v['needed']}, holds {v['available']})"
            )
    clauses = [c.strip() for c in CLAUSE.split(low)]
    for outcome, fits in facts["outcomes"].items():
        word = OUTCOME_WORDS[outcome]
        mentions = [c for c in clauses if word in c]
        if not mentions:
            problems.append(f"does not say whether {word}ing fits")
        for c in mentions:
            says_not = any(x in c for x in NOT_FIT)
            says_fits = any(x in c + " " for x in FIT) and not NEGATION.search(c)
            if fits and not says_fits:
                problems.append(f"does not say plainly that {word}ing fits")
            if not fits and not says_not:
                problems.append(f"suggests {word}ing works, but it does not fit")
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
