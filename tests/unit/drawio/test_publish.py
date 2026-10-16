from fractions import Fraction as F

from open_apprentice.drawio.classify import classify
from open_apprentice.drawio.parse import load_drawio
from open_apprentice.drawio.patch import plan_edits
from open_apprentice.drawio.publish import publish
from open_apprentice.drawio.render import parse_render
from open_apprentice.drawio.scene import build_scene
from open_apprentice.storage.store import LocalStore
from tests.unit.drawio.fixtures import drawio, label, model, node

M = model([node("n1", 40, 40, 100, 50), node("n2", 300, 40, 100, 50), label("l1", 50, 100)])


def fake_render(page, *, shift=(2, 3), size=(30, 14)):
    """Stands in for the engine: a label renders at geometry + shift, nodes at their geometry."""
    c = classify(page)
    labels, nodes = {}, {}
    for cid in c.movable + c.fixed:
        x, y, w, h = (float(v) for v in c.absolute[cid])
        if cid in c.movable:
            labels[cid] = {
                "box": {"x": x + shift[0], "y": y + shift[1], "w": size[0], "h": size[1]},
                "lines": 1,
            }
        else:
            nodes[cid] = {"state": {"x": x, "y": y, "w": w, "h": h}, "element": None}
    return parse_render({"labels": labels, "nodes": nodes, "profile": {"viewer_sha256": "test"}})


def prepare(targets):
    f = load_drawio(drawio(M))
    page = f.pages[0]
    before = build_scene(classify(page), fake_render(page), {"l1": ("n1", "note")}, f.doc_hash)
    return f, before, plan_edits(page, before.offsets, targets)


def test_valid_move_publishes_a_new_artifact_and_reports_axes_separately(tmp_path):
    targets = {"l1": (F(150), F(58))}
    f, before, edits = prepare(targets)
    store = LocalStore(tmp_path)
    r = publish(store, "out/a.drawio", f, 0, edits, targets, before, fake_render)
    assert r.published and store.get("out/a.drawio") is not None
    assert r.conformance["ok"] and r.preservation["ok"] and r.layout["ok"] and r.intent is None
    row = r.conformance["labels"]["l1"]
    assert (row["exact"], row["serialized"], row["measured"]) == (
        ["148", "55"],
        [148, 55],
        ["150", "58"],
    )
    assert "connector crossings are not checked" in " ".join(r.notes)
    assert "not measured" in " ".join(r.notes)


def test_rounding_into_a_neighbour_blocks_publication(tmp_path):
    targets = {
        "l1": (F(541, 2), F(58))
    }  # exact x 268.5 serializes to 269, so the box ends at 301 > n2.x
    f, before, edits = prepare(targets)
    store = LocalStore(tmp_path)
    r = publish(store, "out/b.drawio", f, 0, edits, targets, before, fake_render)
    assert not r.published and not r.layout["ok"] and store.get("out/b.drawio") is None
    row = r.conformance["labels"]["l1"]
    assert row["exact"] != [str(v) for v in row["serialized"]]


def test_renderer_disagreement_fails_conformance_only(tmp_path):
    targets = {"l1": (F(150), F(58))}
    f, before, edits = prepare(targets)
    r = publish(
        LocalStore(tmp_path),
        "out/c.drawio",
        f,
        0,
        edits,
        targets,
        before,
        lambda p: fake_render(p, shift=(4, 3)),
    )
    assert not r.published and not r.conformance["ok"] and r.preservation["ok"]


def test_existing_key_is_never_overwritten(tmp_path):
    targets = {"l1": (F(150), F(58))}
    f, before, edits = prepare(targets)
    store = LocalStore(tmp_path)
    store.create("out/d.drawio", b"other")
    r = publish(store, "out/d.drawio", f, 0, edits, targets, before, fake_render)
    assert not r.published and store.get("out/d.drawio").data == b"other"
