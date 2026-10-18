import threading
import time

import httpx

from open_apprentice.drawio import render
from tests.unit.drawio.test_review_fixes_p3 import model, node
from open_apprentice.drawio.parse import load_drawio


def test_renders_queue_instead_of_exceeding_the_engine_limit(monkeypatch):
    page = load_drawio(
        (
            '<mxfile><diagram id="a" name="P">' + model([node("n1", 0, 0)]) + "</diagram></mxfile>"
        ).encode()
    ).pages[0]
    live = peak = 0
    lock = threading.Lock()

    def post(url, json, timeout):
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        time.sleep(0.05)
        with lock:
            live -= 1
        return httpx.Response(200, json={"labels": {}, "translate": {"x": 0, "y": 0}})

    monkeypatch.setattr(render.httpx, "post", post)
    ts = [threading.Thread(target=lambda: _try(page)) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert peak <= render.MAX_CONCURRENT


def _try(page):
    try:
        render.render_page(page, "http://x")
    except Exception:
        pass
