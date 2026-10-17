"""Real-file episodes (spec 7 real-file corpus; evaluator side). Each .drawio file's first page becomes a scene through
the same pipeline as the product: parse, classify, render in the engine, propose and confirm the label mapping, build the
scene. Episode k demonstrates the frozen behaviour on file k and is scored on the other files, which are fresh to the
learner. A committed rule must also pass the publish checks on each scoring file (conformance, preservation, layout)
wherever the true behaviour passes them. Reported separately, as within-family generalisation."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Optional

from open_apprentice.drawio import mapping as mp
from open_apprentice.drawio.classify import classify
from open_apprentice.drawio.parse import DrawioRefused, load_drawio
from open_apprentice.drawio.patch import plan_edits
from open_apprentice.drawio.publish import publish
from open_apprentice.drawio.render import render_page
from open_apprentice.drawio.scene import DrawioScene, build_scene
from open_apprentice.evaluation.battery_v2 import Episode, FrozenMismatch, _after, _mark
from open_apprentice.evaluation.specs_v2 import VSpec, oracle_v
from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching.step import run_output


def _read(path: Path, expected: Optional[str]) -> bytes:
    """The file's bytes, refused if they differ from the recorded hash (a changed file would change the scoring)."""
    raw = Path(path).read_bytes()
    got = hashlib.sha256(raw).hexdigest()
    if expected is not None and got != expected:
        raise FrozenMismatch(f"{Path(path).name} hash {got} does not match its recorded hash")
    return raw


def _page(path: Path, engine_url: str, expected: Optional[str] = None) -> tuple:
    f = load_drawio(_read(path, expected))
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
    files: list[Path],
    k: int,
    spec: VSpec,
    engine_url: str,
    ep_id: str,
    expected: Optional[list[str]] = None,
) -> Episode:
    """Episode k demonstrates on file k, shows file k+1 as the unlabelled batch document (without a batch no preview is
    possible, so nothing could ever be committed) and is scored on the remaining file(s), which the learner never saw
    (Plan 6 review C1)."""
    scenes = [
        _page(p, engine_url, expected[i] if expected else None)[2].scene
        for i, p in enumerate(files)
    ]
    order = [(k + i) % len(scenes) for i in range(len(scenes))]
    demo, batch, scoring = scenes[order[0]], scenes[order[1]], [scenes[i] for i in order[2:]]
    demos = [(demo, _after(spec, demo))]
    return Episode(
        ep_id,
        "real_file",
        spec,
        [demo],
        [demos[0][1]],
        [batch],
        scoring,
        _mark(demos),
        None,
        seed=0,
        meta={
            "files": [str(files[i]) for i in order],
            "demo_file": 0,
            **({"sha256": [expected[i] for i in order]} if expected else {}),
        },
    )


def _receipt(path: Path, rule_targets: dict, engine_url: str, sha: Optional[str] = None) -> object:
    """The publish receipt, or the refusal text when the edited page cannot even be published (e.g. off the page)."""
    f, page, ds = _page(path, engine_url, sha)
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
    hashes = ep.meta.get("sha256") or [None] * len(ep.meta["files"])
    for path, sha in list(zip(ep.meta["files"], hashes))[
        2:
    ]:  # the files after the demonstration and the batch
        path = Path(path)
        ds = _page(path, engine_url, sha)[2]
        got = _receipt(path, _targets(rule, ds), engine_url, sha)
        want = _receipt(path, _targets(ep.spec, ds), engine_url, sha)
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
