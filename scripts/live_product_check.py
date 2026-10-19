"""Product model check (docs/evaluation/product_model_check.md): drives one live teaching session through the public API of
a running server, with a scripted teacher who wants 'every note left-aligned under its box, 8 below', then applies the
committed skill to six unseen library diagrams and scores the placement. Appends one row to
results/product_model_check/rows.jsonl.

    uv run python scripts/live_product_check.py http://127.0.0.1:8790 <label>
"""

from __future__ import annotations

import json
import os
import sys
import time
from fractions import Fraction as F
from pathlib import Path

import httpx

LIB = Path("apps/web/public/samples/library")
DEMO, BATCH, HELD = ["000"], ["001", "002", "003", "004", "005"], ["006", "007", "008", "009", "010", "011"]
GAP = 8
TERMINAL = {"committed", "failed", "cancelled"}


def files(prefixes: list[str]) -> list[Path]:
    return [next(LIB.glob(f"{p}-*.drawio")) for p in prefixes]


def num(v: str) -> F:
    return F(v)


class Api:
    def __init__(self, base: str) -> None:
        self.c = httpx.Client(base_url=base.rstrip("/") + "/api/v2", timeout=120)

    def get(self, path: str) -> dict:
        r = self.c.get(path)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, body: dict) -> dict:
        r = self.c.post(path, json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"{path}: {r.status_code} {r.text[:300]}")
        return r.json()

    def upload(self, f: Path) -> str:
        r = self.c.post(f"/documents?name={f.name}", content=f.read_bytes(), headers={"content-type": "application/octet-stream"})
        r.raise_for_status()
        return r.json()["doc_id"]

    def ready(self, doc_id: str) -> dict:
        """Wait for the render, confirm the suggested mapping, return a document reference."""
        for _ in range(240):
            d = self.get(f"/documents/{doc_id}")
            if d["render"] != "pending":
                break
            time.sleep(0.5)
        p = d["pages"][0]
        mh = p["mapping_hash"] or self.post(f"/documents/{doc_id}/mapping", {"page_id": p["page_id"], "labels": {}, "confirm": True})["mapping_hash"]
        return {"doc_id": doc_id, "page_id": p["page_id"], "mapping_hash": mh}

    def scene(self, ref: dict) -> dict:
        return self.get(f"/documents/{ref['doc_id']}/pages/{ref['page_id']}/scene?mapping_hash={ref['mapping_hash']}")


def intended(scene: dict) -> dict[str, tuple[F, F]]:
    objs = {o["id"]: o for o in scene["objects"]}
    out = {}
    for o in scene["objects"]:
        if o["kind"] == "label" and o["id"] in scene["movable"]:
            a = objs[o["attached"]]
            out[o["id"]] = (num(a["x"]), num(a["y"]) + num(a["h"]) + GAP)
    return out


def matches(output: dict, want: dict[str, tuple[F, F]]) -> bool:
    return all(
        k in output and abs(num(str(output[k][0])) - x) <= F(1, 2) and abs(num(str(output[k][1])) - y) <= F(1, 2)
        for k, (x, y) in want.items()
    )


def scene_of(api: Api, scene_id: str, refs: dict[str, dict]) -> dict | None:
    doc_id, page_id = scene_id.split(":", 1)
    ref = refs.get(doc_id)
    if ref is None:  # a generated probe document, owned by this session's owner
        p = api.get(f"/documents/{doc_id}")["pages"][0]
        if not p.get("mapping_hash"):
            return None
        ref = {"doc_id": doc_id, "page_id": page_id, "mapping_hash": p["mapping_hash"]}
    return api.scene(ref)


def answer(api: Api, req: dict, refs: dict[str, dict]) -> dict:
    if req["type"] == "ChooseOutput":
        sc = scene_of(api, req["scene_id"], refs)
        want = intended(sc) if sc else {}
        pick = next((a for a, out in req["alternatives"] if want and matches(out, want)), None)
        return {"kind": "choose", "selected": pick} if pick else {"kind": "none"}
    if req["type"] == "ConfirmPreview":
        per = []
        for item_id, scene_id, _, out in req["items"]:
            sc = scene_of(api, scene_id, refs)
            per.append([item_id, "approve" if sc and matches(out, intended(sc)) else "reject"])
        return {"kind": "items", "per_item": per}
    return {"kind": "unsure"}


def main(base: str, label: str) -> None:
    api = Api(base)
    t_import = time.monotonic()
    ids = {p: api.upload(f) for p, f in zip(DEMO + BATCH + HELD, files(DEMO + BATCH + HELD))}
    refs = {p: api.ready(i) for p, i in ids.items()}
    by_doc = {r["doc_id"]: r for r in refs.values()}
    demo = refs[DEMO[0]]
    sc = api.scene(demo)
    boxes = {k: [str(x), str(y)] for k, (x, y) in intended(sc).items()}
    docs = [demo] + [refs[p] for p in BATCH]
    print(f"[{label}] imported in {time.monotonic() - t_import:.0f}s; starting the live session", flush=True)
    t0 = time.monotonic()
    teacher = 0.0
    sid = api.post("/sessions", {"documents": docs, "demonstrations": [{"document_ref": 0, "before_scene_hash": sc["scene_hash"], "boxes": boxes}],
                                 "live": os.environ.get("CHECK_LIVE", "1") == "1", "idempotency_key": f"check-{label}-{int(time.time())}"})["session_id"]
    first_q = None
    answers = []
    while True:
        s = api.get(f"/sessions/{sid}")
        if s["state"] in TERMINAL or time.monotonic() - t0 > 1200:
            break
        q = s["outstanding"]
        if q is not None:
            first_q = first_q or round(time.monotonic() - t0 - teacher, 1)
            ta = time.monotonic()
            body = answer(api, q["request"], by_doc)
            answers.append({"type": q["request"]["type"], "answer": body["kind"]})
            api.post(f"/sessions/{sid}/responses", {"request_id": q["request_id"], "intent_revision": q["intent_revision"], **body})
            teacher += time.monotonic() - ta
        time.sleep(2)
    seconds = round(time.monotonic() - t0 - teacher, 1)
    row = {"label": label, "session": sid, "state": s["state"], "reason": s["result"].get("reason"), "seconds": seconds,
           "first_question_s": first_q, "answers": answers, "spend_recorded": s["spend"]["recorded"],
           "spend_uncertain": s["spend"]["uncertain"], "thinking": s.get("thinking"), "outcome": "no commit"}
    if s["state"] == "committed":
        skill = s["result"]["skill_id"]
        for _ in range(60):
            if api.get(f"/skills/{skill}")["active"]["version"]:
                break
            time.sleep(1)
        held = [refs[p] for p in HELD]
        run = api.post(f"/skills/{skill}/versions/1/apply", {"documents": held, "idempotency_key": f"held-{sid}"})
        for _ in range(300):
            r = api.get(f"/runs/{run['run_id']}")
            if r["status"] != "running":
                break
            time.sleep(1)
        ok = 0
        for ref in held:
            res = r["results"].get(f"{ref['doc_id']}:{ref['page_id']}", {})
            want = intended(api.scene(ref))
            exact = {k: v["measured"] for k, v in ((res.get("receipt") or {}).get("conformance") or {}).get("labels", {}).items()}
            ok += bool(exact) and matches(exact, want)
        row.update(held_correct=ok, held_total=len(held), outcome="success" if ok == len(held) else "wrong commit")
    out = Path("results/product_model_check")
    out.mkdir(parents=True, exist_ok=True)
    with (out / "rows.jsonl").open("a") as f:
        f.write(json.dumps(row) + "\n")
    print(json.dumps({k: v for k, v in row.items() if k != "thinking"}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
