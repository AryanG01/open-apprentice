"""Drive the live demo API end to end against a RUNNING server (use --mode nemotron to spend model credit; the server's own cap applies).
Prints what each step did, how long it took, and the metered cost. Usage: python scripts/live_flow_check.py --mode nemotron"""

import argparse
import json
import time

import httpx

ap = argparse.ArgumentParser()
ap.add_argument("--mode", default="reference")
ap.add_argument("--base", default="http://127.0.0.1:8000")
a = ap.parse_args()
c = httpx.Client(base_url=a.base, timeout=600)


def step(name, fn):
    t0 = time.time()
    r = fn()
    dt = time.time() - t0
    if r.status_code >= 400:
        print(f"[{name}] HTTP {r.status_code} after {dt:.0f}s: {r.text[:300]}")
        raise SystemExit(1)
    j = r.json()
    m = j.get("meter")
    print(
        f"[{name}] {dt:5.0f}s  "
        + (
            f"model_calls={m['session_calls']} tokens={m['session_tokens']} session_usd={m['session_usd']} server_usd={m['server_spend_usd']}"
            if m
            else ""
        )
    )
    return j


st = step("start", lambda: c.post("/api/teach", json={"mode": a.mode}))
print(
    "   state:",
    st["state"],
    "| candidates:",
    st["candidate_count"],
    "| label:",
    st["label"]["mode"],
)
for _ in range(3):
    if st["state"] != "AWAITING_USER" or "question" not in st:
        break
    q = st["question"]
    print("   question source:", q["source"], "options:", [o["id"] for o in q["options"]])
    st = step(
        "answer",
        lambda: c.post(
            f"/api/teach/{st['id']}/answer",
            json={
                "query_id": q["query_id"],
                "answer": q["options"][0]["id"],
                "candidate_set_hash": q["candidate_set_hash"],
            },
        ),
    )
print(
    "   state:", st["state"], "|", (st.get("concept") or {}).get("rule_text"), "|", st["note"][:100]
)
if st["state"] != "INTENT_READY":
    raise SystemExit("did not reach INTENT_READY (an honest outcome; nothing to run)")
sid = st["id"]
for backend, tc in (("konva", False), ("fabric", False), ("fabric", True)):
    r = step(
        f"run {backend} tool_change={tc}",
        lambda: c.post(
            f"/api/teach/{sid}/run", json={"width": 300, "backend": backend, "tool_change": tc}
        ),
    )
    print(
        "   verifier_passed:",
        r["verifier_passed"],
        "| binding origin:",
        r["binding"]["origin"],
        "| fallbacks:",
        r["fallbacks"],
    )
if r["can_repair"]:
    f = step("repair", lambda: c.post(f"/api/teach/{sid}/repair"))
    print(
        "   status:",
        f["status"],
        "| rule_unchanged:",
        f["rule_unchanged"],
        "| attempts:",
        [(x["source"], x["failed_stage"]) for x in f["attempts"]],
        "| fallbacks:",
        f["fallbacks"],
    )
    for tc in (True, False):
        r = step(
            f"re-run fabric tool_change={tc}",
            lambda: c.post(
                f"/api/teach/{sid}/run", json={"width": 220, "backend": "fabric", "tool_change": tc}
            ),
        )
        print("   verifier_passed:", r["verifier_passed"])
print(json.dumps(c.get("/health/ready").json()["model"]))
