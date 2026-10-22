"""One measurement of what Nemotron adds in the campaign lane (plan 9E), against each deterministic baseline:
role proposals vs the heuristic, explanations vs the template, native procedures vs the reference. Development fixtures
only. The live run goes through SpendGuard with a run cap; without it the same code runs on a mock provider."""

from __future__ import annotations

import asyncio
import datetime
import pathlib
import tempfile

from open_apprentice.budget import Ledger, Limits
from open_apprentice.campaign.explain import explain, overflow_facts
from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.learn import learn_layout
from open_apprentice.campaign.model_procedures import write_procedure
from open_apprentice.campaign.preferences import PreferenceStore
from open_apprentice.campaign.roles import heuristic_roles, propose_roles
from open_apprentice.campaign.run import close_run, start_run
from open_apprentice.evaluation.campaign_procedure_check import check_procedure
from open_apprentice.evaluation.harness import EvaluatorHarness
from open_apprentice.providers.base import Provider
from open_apprentice.storage.store import LocalStore

ROLE_BANNERS = ("teach_before", "short_a", "short_b", "de_long_a", "de_long_b", "fr_long")
OVERFLOW_BANNERS = ("de_long_a", "de_long_b", "fr_long")
OWNER = "campaign-nemotron"


def _strip(scene: dict) -> tuple[dict, dict]:
    truth = {n["id"]: n["role"] for n in scene["nodes"] if n.get("role")}
    untagged = {
        **scene,
        "nodes": [{k: v for k, v in n.items() if k != "role"} for n in scene["nodes"]],
    }
    return untagged, truth


def measure(provider: Provider, engine_url: str, token: str) -> dict:
    """One event loop for the whole measurement: a live provider's HTTP client cannot cross loops."""
    return asyncio.run(measure_async(provider, engine_url, token))


async def measure_async(provider: Provider, engine_url: str, token: str) -> dict:
    ledger = Ledger(Limits(tokens=400_000, calls=40))
    harness = EvaluatorHarness(engine_url, token)
    roles = []
    for fid in ROLE_BANNERS:
        scene, truth = _strip(load_fixture(fid)["scene"])
        p = await propose_roles(provider, ledger, scene, "banner")
        roles.append(
            {
                "banner": fid,
                "model_used": p.origin == "model",
                "model_correct": p.origin == "model" and p.mapping == truth,
                "heuristic_correct": heuristic_roles(scene, "banner") == truth,
                "rejected_because": p.problems,
            }
        )
    learned = await learn_layout(
        load_fixture("teach_before")["scene"], load_fixture("teach_after")["scene"]
    )

    def question(f: dict):
        with tempfile.TemporaryDirectory() as tmp:
            run = start_run(
                f["scene"],
                f["locale"],
                learned,
                lambda s: harness.open_session(s, OWNER)[0],
                PreferenceStore(LocalStore(pathlib.Path(tmp))),
            )
            close_run(run)
        return run

    explanations = []
    for fid in OVERFLOW_BANNERS:
        f = load_fixture(fid)
        run = await asyncio.to_thread(question, f)
        e = await explain(provider, ledger, overflow_facts(run, f["scene"]))
        explanations.append(
            {"banner": fid, "origin": e.origin, "text": e.text, "rejected_because": e.problems}
        )
    procedures = []
    for backend in ("konva", "fabric"):
        out = await write_procedure(
            provider,
            ledger,
            backend,
            lambda prog, b=backend: check_procedure(prog, b, engine_url, token),
        )
        procedures.append({"backend": backend, "origin": out.origin, "attempts": out.attempts})
    snap = ledger.snapshot()
    return {
        "model": getattr(provider, "requested_model", "?"),
        "label": getattr(provider, "label", "?"),
        "roles": roles,
        "explanations": explanations,
        "procedures": procedures,
        "tokens": snap["consumed"]["tokens"],
        "ledger_usd": snap["consumed"]["usd"],
    }


def render_markdown(m: dict, *, live: bool, spent_usd: float | None = None) -> str:
    roles, ex, procs = m["roles"], m["explanations"], m["procedures"]
    lines = [
        "# Campaign lane: what Nemotron adds",
        "",
        f"{datetime.date.today().isoformat()} · model `{m['model']}` ({'live, Nebius Token Factory' if live else 'MOCK provider: format check, not a result'}) · "
        f"{m['tokens']} tokens"
        + (f" · ${spent_usd:.3f} spent (ledger)" if spent_usd is not None else "")
        + ". Development fixtures, not held out.",
        "",
        "## Role proposals (banner shown with its roles removed; correct = exactly the authored roles)",
        "",
        f"Nemotron correct on **{sum(r['model_correct'] for r in roles)} of {len(roles)}**; heuristic correct on "
        f"**{sum(r['heuristic_correct'] for r in roles)} of {len(roles)}**.",
        "",
        "| banner | Nemotron used | Nemotron correct | heuristic correct | Nemotron rejected because |",
        "|---|---|---|---|---|",
    ]
    lines += [
        f"| {r['banner']} | {'yes' if r['model_used'] else 'no'} | {'yes' if r['model_correct'] else 'no'} | "
        f"{'yes' if r['heuristic_correct'] else 'no'} | {'; '.join(r['rejected_because']) or '-'} |"
        for r in roles
    ]
    lines += [
        "",
        "## Overflow explanations (used only if every stated number and element matches the measured facts)",
        "",
        f"Nemotron's wording used on **{sum(e['origin'] == 'model' for e in ex)} of {len(ex)}**; otherwise the template.",
        "",
        "| banner | used | text shown | rejected because |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {e['banner']} | {e['origin']} | {e['text']} | {'; '.join(e['rejected_because']) or '-'} |"
        for e in ex
    ]
    lines += [
        "",
        "## Native procedures (accepted only if the verifier passes a seen banner and two new ones)",
        "",
        "| engine | accepted | attempts | cases passed per attempt |",
        "|---|---|---|---|",
    ]
    for p in procs:
        per = [
            f"{sum(c['passed'] for c in a['cases'])} of {len(a['cases'])}" for a in p["attempts"]
        ]
        lines.append(
            f"| {p['backend']} | {'Nemotron' if p['origin'] == 'model' else 'no: reference kept'} | {len(p['attempts'])} | {', '.join(per) or '-'} |"
        )
    return "\n".join(lines) + "\n"
