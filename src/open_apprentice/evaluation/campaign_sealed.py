"""Private sealed set for the campaign lane (spec 7.8, 7.9; plan 9D). The banners and their gold are authored by the owner
in the private, git-ignored folder the CLI passes in (docs/evaluation/campaign_sealed_howto.md); only a hash manifest
is committed. This module validates, seals and runs
the set; it never generates any of its contents. Agent-visible packages never import it (import-linter)."""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import pathlib
import tempfile

from open_apprentice.campaign.fixtures import FIXTURE_IDS, load_fixture
from open_apprentice.campaign.learn import learn_layout
from open_apprentice.campaign.preferences import PreferenceStore
from open_apprentice.campaign.run import answer, close_run, start_run
from open_apprentice.campaign.scene import RoleError, role_map
from open_apprentice.evaluation.campaign_verifier import verify_story
from open_apprentice.evaluation.harness import EvaluatorHarness
from open_apprentice.evaluation.text_layout import _manifest
from open_apprentice.storage.store import LocalStore

BACKENDS = ("konva", "fabric")
OUTCOMES = ("layout", "shrink", "split")
BUILTIN = {"shrink": "builtin_shrink_hero", "split": "builtin_split_two_cards"}
OWNER = "campaign-sealed"


class SealError(Exception):
    pass


def _banners(root: pathlib.Path) -> list[tuple[pathlib.Path, dict]]:
    return [
        (p, json.loads(p.read_text(encoding="utf-8")))
        for p in sorted((root / "banners").glob("*.json"))
    ]


def validate_set(root: pathlib.Path) -> list[str]:
    """Every problem that would make the set unusable or not held out; empty means valid."""
    problems: list[str] = []
    assets = {
        k.split("/", 1)[1].rsplit(".", 1)[0]
        for k in _manifest()["files"]
        if k.startswith("assets/")
    }
    seen: dict[str, str] = {}
    banners = _banners(root)
    if not banners:
        problems.append(f"no banners under {root / 'banners'}")
    for path, b in banners:
        bid = b.get("id", "")
        if bid in seen:
            problems.append(f"duplicate banner id {bid} ({seen[bid]} and {path.name})")
        seen.setdefault(bid, path.name)
        if bid in FIXTURE_IDS:
            problems.append(f"banner id {bid} collides with a public development fixture")
        boards = [
            n["id"] for n in b.get("scene", {}).get("nodes", []) if n.get("type") == "artboard"
        ]
        try:
            if len(boards) != 1:
                raise RoleError([f"expected one artboard, found {len(boards)}"])
            role_map(b["scene"], boards[0])
        except (RoleError, KeyError) as e:
            problems.append(f"{bid}: {e}")
        for n in b.get("scene", {}).get("nodes", []):
            if n.get("type") == "text" and n.get("fontFamily") != "Liberation Sans":
                problems.append(
                    f"{bid}/{n['id']}: font {n.get('fontFamily')} is not the vendored Liberation Sans"
                )
            if n.get("type") == "image" and n.get("asset") not in assets:
                problems.append(f"{bid}/{n['id']}: unknown asset {n.get('asset')}")
        outcomes = b.get("expected_outcomes") or []
        if not outcomes or any(o not in OUTCOMES for o in outcomes):
            problems.append(
                f"{bid}: expected_outcomes must be a non-empty subset of {list(OUTCOMES)}"
            )
        for o in outcomes:
            if not (root / "gold" / f"{bid}.{o}.json").is_file():
                problems.append(f"{bid}: missing gold for outcome {o}")
    return problems


def _hashes(root: pathlib.Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*.json"))
        if p.is_file()
    }


def seal(root: pathlib.Path, manifest: pathlib.Path) -> dict:
    problems = validate_set(root)
    if problems:
        raise SealError("the set is not valid: " + "; ".join(problems))
    files = _hashes(root)
    combined = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    body = {
        "sealed_at": datetime.date.today().isoformat(),
        "files": files,
        "combined_sha256": combined,
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(body, indent=1) + "\n")
    return body


def check_sealed(root: pathlib.Path, manifest: pathlib.Path) -> None:
    """Everything a run needs before it may touch an engine: a manifest, a valid set, and no file changed since sealing."""
    if not manifest.is_file():
        raise SealError(
            f"no manifest at {manifest}: author the set and run `oa eval campaign-seal` first"
        )
    problems = validate_set(root)
    if problems:
        raise SealError("the set is not valid: " + "; ".join(problems))
    _check_seal(root, manifest)


def _check_seal(root: pathlib.Path, manifest: pathlib.Path) -> None:
    want = json.loads(manifest.read_text())["files"]
    got = _hashes(root)
    changed = sorted(k for k in set(want) | set(got) if want.get(k) != got.get(k))
    if changed:
        raise SealError("the set changed since it was sealed: " + ", ".join(changed))


def run_sealed(
    root: pathlib.Path, manifest: pathlib.Path, engine_url: str, token: str, out_dir: pathlib.Path
) -> dict:
    """Learn from the PUBLIC teaching pair only, run every sealed banner on both backends, answer a question with the
    gold's outcome (recorded as such), and verify against the sealed gold. Refuses a set that changed since sealing.
    """
    check_sealed(root, manifest)  # before any engine call
    learned = asyncio.run(
        learn_layout(load_fixture("teach_before")["scene"], load_fixture("teach_after")["scene"])
    )
    harness = EvaluatorHarness(engine_url, token)
    rows = []
    for _, b in _banners(root):
        for backend in BACKENDS:
            for outcome in b["expected_outcomes"]:
                gold = json.loads(
                    (root / "gold" / f"{b['id']}.{outcome}.json").read_text(encoding="utf-8")
                )
                row = {"banner": b["id"], "backend": backend, "outcome": outcome, "answered": None}
                with (
                    tempfile.TemporaryDirectory() as tmp
                ):  # no saved preference: each banner is judged on its own
                    prefs = PreferenceStore(LocalStore(pathlib.Path(tmp)))
                    run = start_run(
                        b["scene"], b["locale"], learned,
                        lambda scene: harness.open_session(scene, OWNER, backend=backend)[0], prefs,
                    )  # fmt: skip
                    try:
                        if run.status == "question" and outcome in BUILTIN:
                            preview = run.previews.get(BUILTIN[outcome])
                            if preview is not None and preview.fits:
                                answer(
                                    run,
                                    BUILTIN[outcome],
                                    prefs,
                                    None,
                                    current_source_hash=run.source_hash,
                                )
                                row["answered"] = BUILTIN[outcome]
                        row["status"] = run.status
                        expected_status = "ready" if outcome == "layout" else "applied"
                        if run.status == expected_status and run.result_session:
                            native = harness.native(run.result_session, OWNER)
                            report = verify_story(
                                b["scene"],
                                native,
                                gold.get("scene") if gold.get("applicable", True) else None,
                            )
                            row.update(passed=report.passed, failed_checks=report.failed())
                        else:
                            row.update(
                                passed=False,
                                failed_checks=[f"status {run.status}, expected {expected_status}"],
                            )
                    finally:
                        close_run(run)
                rows.append(row)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "rows.json").write_text(json.dumps(rows, indent=1))
    passed = sum(r["passed"] for r in rows)
    lines = [
        "# Campaign lane: private sealed set",
        "",
        f"Run {datetime.date.today().isoformat()} against manifest `{json.loads(manifest.read_text())['combined_sha256'][:16]}…`. "
        f"Learned from the public teaching pair only (origin `{learned.origin}`); questions answered with the gold outcome.",
        "",
        f"**{passed} of {len(rows)} rows pass.**",
        "",
        "| banner | outcome | backend | status | verifier | failed checks |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {r['banner']} | {r['outcome']} | {r['backend']} | {r['status']} | {'pass' if r['passed'] else 'FAIL'} | "
        f"{', '.join(r['failed_checks']) or '-'} |"
        for r in rows
    ]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n")
    return {"rows": rows, "passed": passed, "total": len(rows)}
