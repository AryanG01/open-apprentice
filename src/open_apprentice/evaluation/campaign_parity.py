"""Cross-backend parity for the campaign lane (plan 9D): one learned rule, one reference procedure, every development
fixture/outcome on Konva and Fabric, judged by the independent verifier against the authored gold."""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import pathlib
import subprocess
import tempfile

from open_apprentice.campaign.builtins import shrink_hero, split_two_cards
from open_apprentice.campaign.fixtures import FIXTURE_IDS, load_fixture
from open_apprentice.campaign.layout_rule import evaluate_layout, objects_for_rule, wrap_learned
from open_apprentice.campaign.learn import learn_layout
from open_apprentice.campaign.plan import plan_from_layout
from open_apprentice.campaign.preferences import PreferenceStore
from open_apprentice.campaign.procedures import apply_plan
from open_apprentice.campaign.run import close_run, start_run
from open_apprentice.evaluation.campaign_gold import GOLD_KEYS, load_gold
from open_apprentice.evaluation.campaign_verifier import verify_story
from open_apprentice.evaluation.harness import EvaluatorHarness
from open_apprentice.storage.store import LocalStore

BACKENDS = ("konva", "fabric")
OWNER = "campaign-parity"
TRANSFORM = {"layout": lambda p: p, "shrink": shrink_hero, "split": split_two_cards}
ROOT = pathlib.Path(__file__).resolve().parents[3]


def parity_table(engine_url: str, token: str) -> dict:
    learned = asyncio.run(
        learn_layout(load_fixture("teach_before")["scene"], load_fixture("teach_after")["scene"])
    )
    harness = EvaluatorHarness(engine_url, token)
    verifier_rows, run_rows = [], []
    for backend in BACKENDS:
        for fid, outcome in GOLD_KEYS:
            gold = load_gold(fid, outcome)
            if gold is None:
                continue
            src = load_fixture(fid)["scene"]
            out = evaluate_layout(
                wrap_learned(learned.rule),
                objects_for_rule(src, "banner"),
                {"output_format": "9:16", "overflows": False},
            )
            plan = TRANSFORM[outcome](plan_from_layout(out, src, "banner", learned.origin))
            session, _ = harness.open_session(src, OWNER, backend=backend)
            try:
                apply_plan(session, plan)
                report = verify_story(src, harness.native(session.session_id, OWNER), gold["scene"])
            finally:
                session.close()
            verifier_rows.append(
                {
                    "fixture": fid,
                    "outcome": outcome,
                    "backend": backend,
                    "passed": report.passed,
                    "failed_checks": report.failed(),
                }
            )
        with (
            tempfile.TemporaryDirectory() as tmp
        ):  # no saved preferences: overflowing banners must ask
            prefs = PreferenceStore(LocalStore(pathlib.Path(tmp)))
            for fid in FIXTURE_IDS:
                if fid in ("teach_before", "teach_after"):
                    continue
                f = load_fixture(fid)
                run = start_run(
                    f["scene"], f["locale"], learned,
                    lambda scene: harness.open_session(scene, OWNER, backend=backend)[0], prefs,
                )  # fmt: skip
                close_run(run)
                run_rows.append({"fixture": fid, "backend": backend, "status": run.status})
    return {
        "rule_sha256": hashlib.sha256(
            json.dumps(learned.rule, sort_keys=True).encode()
        ).hexdigest(),
        "learned_origin": learned.origin,
        "verifier_rows": verifier_rows,
        "run_rows": run_rows,
    }


def _versions() -> dict[str, str]:
    out = {}
    for lib in ("konva", "fabric"):
        for base in (ROOT / "node_modules", ROOT / "services" / "engine" / "node_modules"):
            pkg = base / lib / "package.json"
            if pkg.is_file():
                out[lib] = json.loads(pkg.read_text())["version"]
                break
    try:
        out["commit"] = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        out["commit"] = "unknown"
    return out


def render_markdown(t: dict) -> str:
    v = _versions()
    rows = t["verifier_rows"]
    passed = sum(r["passed"] for r in rows)
    lines = [
        "# Campaign lane: Konva / Fabric parity",
        "",
        f"Generated {datetime.date.today().isoformat()} at commit `{v.get('commit')}` (Konva {v.get('konva', '?')}, "
        f"Fabric {v.get('fabric', '?')}) by `oa eval campaign-parity`. Public development fixtures, not held out.",
        "",
        f"One learned rule for both backends (origin `{t['learned_origin']}`, sha256 `{t['rule_sha256'][:16]}…`), the same "
        "reference procedure, built-in outcomes labelled as such. Each row is the independent verifier against the authored gold.",
        "",
        "Fabric measures text with its own metrics (a 1.13 font-size multiplier), so a banner whose copy sits close to a "
        "frame limit can come back `ready` on Konva and `question` on Fabric; the run-status table below shows whether that "
        "happened for these fixtures.",
        "",
        f"**{passed} of {len(rows)} rows pass.**",
        "",
        "| fixture | outcome | backend | verifier | failed checks |",
        "|---|---|---|---|---|",
    ]
    lines += [
        f"| {r['fixture']} | {r['outcome']} | {r['backend']} | {'pass' if r['passed'] else 'FAIL'} | "
        f"{', '.join(r['failed_checks']) or '-'} |"
        for r in rows
    ]
    lines += [
        "",
        "## Run status per banner (no saved preference)",
        "",
        "| fixture | konva | fabric |",
        "|---|---|---|",
    ]
    by = {(r["fixture"], r["backend"]): r["status"] for r in t["run_rows"]}
    for fid in dict.fromkeys(r["fixture"] for r in t["run_rows"]):
        lines.append(f"| {fid} | {by.get((fid, 'konva'), '-')} | {by.get((fid, 'fabric'), '-')} |")
    return "\n".join(lines) + "\n"
