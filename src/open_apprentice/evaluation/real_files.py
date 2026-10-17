"""Real-file episodes (spec 7 real-file corpus; evaluator side). Each .drawio file's first page becomes a scene through
the same pipeline as the product: parse, classify, render in the engine, propose and confirm the label mapping, build the
scene. Episode k demonstrates the frozen behaviour on file k and is scored on the other files, which are fresh to the
learner. A committed rule must also pass the publish checks on each scoring file (conformance, preservation, layout)
wherever the true behaviour passes them. Reported separately, as within-family generalisation."""

from __future__ import annotations

import tempfile
from pathlib import Path

from open_apprentice.drawio import mapping as mp
from open_apprentice.drawio.classify import classify
from open_apprentice.drawio.parse import DrawioRefused, load_drawio
from open_apprentice.drawio.patch import plan_edits
from open_apprentice.drawio.publish import publish
from open_apprentice.drawio.render import render_page
from open_apprentice.drawio.scene import DrawioScene, build_scene
from open_apprentice.evaluation.battery_v2 import Episode, _after, _mark
from open_apprentice.evaluation.specs_v2 import VSpec, oracle_v
from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching.step import run_output


def _page(path: Path, engine_url: str) -> tuple:
    f = load_drawio(Path(path).read_bytes())
    page = f.pages[0]
    c = classify(page)
    r = render_page(page, engine_url, png=False)
    m = mp.confirm(mp.propose(c, r, f.doc_hash), "evaluator")
    return (
        f,
        page,
        build_scene(c, r, mp.as_scene_mapping(m, f.doc_hash, page.id, c.movable), f.doc_hash),
    )


def real_file_episode(
    files: list[Path], k: int, spec: VSpec, engine_url: str, ep_id: str
) -> Episode:
    scenes = [_page(p, engine_url)[2].scene for p in files]
    demo = scenes[k]
    scoring = [s for i, s in enumerate(scenes) if i != k]
    demos = [(demo, _after(spec, demo))]
    return Episode(
        ep_id,
        "real_file",
        spec,
        [demo],
        [demos[0][1]],
        [],
        scoring,
        _mark(demos),
        None,
        seed=0,
        meta={"files": [str(p) for p in files], "demo_file": k},
    )


def _receipt(path: Path, rule_targets: dict, engine_url: str) -> object:
    """The publish receipt, or the refusal text when the edited page cannot even be published (e.g. off the page)."""
    f, page, ds = _page(path, engine_url)
    edits = plan_edits(page, ds.offsets, rule_targets)
    with tempfile.TemporaryDirectory() as d:
        try:
            return publish(
                LocalStore(Path(d)),
                "out.drawio",
                f,
                page.index,
                edits,
                rule_targets,
                ds,
                lambda p: render_page(p, engine_url, png=False),
            )
        except DrawioRefused as e:
            return str(e)


def _targets(rule_or_spec: object, ds: DrawioScene) -> dict:
    if isinstance(rule_or_spec, VSpec):
        moved = oracle_v(rule_or_spec, ds.scene)
    else:
        moved = run_output(rule_or_spec, ds.scene) or {}
    return {k: v for k, v in moved.items() if k in ds.movable}


def publish_failures(ep: Episode, rule: list, engine_url: str) -> list[str]:
    """Publish checks the committed rule fails on a scoring file while the true behaviour passes them."""
    out = []
    files = [Path(p) for i, p in enumerate(ep.meta["files"]) if i != ep.meta["demo_file"]]
    for path in files:
        ds = _page(path, engine_url)[2]
        got = _receipt(path, _targets(rule, ds), engine_url)
        want = _receipt(path, _targets(ep.spec, ds), engine_url)
        for check in ("conformance", "preservation", "layout"):
            if _ok(want, check) and not _ok(got, check):
                out.append(
                    f"{path.name}: {check}" + (f" ({got[:120]})" if isinstance(got, str) else "")
                )
                break
    return out


def _ok(receipt: object, check: str) -> bool:
    if isinstance(receipt, str):  # publish refused the edited page
        return False
    return bool(getattr(receipt, check)["ok"])
