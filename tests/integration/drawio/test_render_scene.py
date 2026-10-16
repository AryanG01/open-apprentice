from open_apprentice.drawio.classify import classify
from open_apprentice.drawio.parse import load_drawio
from open_apprentice.drawio.render import render_page
from open_apprentice.drawio.scene import build_scene


def test_corpus_page_becomes_a_scene(engine_url):
    f = load_drawio(open("tests/fixtures/drawio_corpus/dev/d1.drawio", "rb").read())
    c = classify(f.pages[0])
    r = render_page(f.pages[0], engine_url)
    first_node = next(cid for cid in c.fixed if cid in r.nodes)
    s = build_scene(c, r, {cid: (first_node, "note") for cid in c.movable}, f.doc_hash)
    assert {o["kind"] for o in s.scene["objects"]} >= {"node", "label"}
    assert r.png and r.profile["viewer_sha256"].startswith("bc7586cb")
    for cid in s.movable:
        dx, dy = s.offsets[cid]
        assert abs(dx) < 120 and abs(dy) < 20
