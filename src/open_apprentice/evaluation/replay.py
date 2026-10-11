"""Offline replay of an evidence package (spec 24.5 `oa replay-evidence`). Needs NO engine, NO model and NO network.

It re-derives, from the package alone, everything that can be re-derived: the teaching ledger's hash chain, the domain hash, the sealed concept
hash, the native program's hash and the concept hash it carries, and the layout the rule requires (exact rational arithmetic) compared with the
geometry the engine reported. It also checks that the package's own pass/fail claim agrees with that recomputation. It does NOT re-run the real
engine; the engine-side independent verifier remains the authority for what the browser actually did.
"""

from __future__ import annotations

import json
from fractions import Fraction

from open_apprentice.api.geometry import card_scene
from open_apprentice.concepts.bindings import NATIVE_TOL
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.rules import RuleError, evaluate_rule
from open_apprentice.concepts.schemas import assert_no_aggregate_confidence, sha

REQUIRED = ("concept", "ledger", "domain", "run", "result", "observed_geometry")


def _check(name: str, passed: bool, detail: str = "") -> dict:
    return {"name": name, "passed": bool(passed), "detail": detail}


def _finding(name: str, detail: str) -> dict:
    """Reported, not judged: a package may honestly document a layout that does NOT satisfy the rule (e.g. a tool-change mismatch)."""
    return {"name": name, "passed": None, "detail": detail}


def _ledger_chain(entries: list[dict]) -> tuple[bool, str]:
    prev = "genesis"
    for i, e in enumerate(entries):
        body = {
            "seq": i,
            "kind": e["kind"],
            "payload": e["payload"],
            "source": e["source"],
            "prev": prev,
        }
        if e.get("prev_hash") != prev:
            return False, f"entry {i}: previous-hash link is broken"
        if e.get("hash") != sha(body):
            return False, f"entry {i}: contents do not match their hash (edited after the fact)"
        prev = e["hash"]
    return True, f"{len(entries)} entries, chain intact"


def replay_package(pkg: dict) -> dict:
    checks: list[dict] = []
    missing = [k for k in REQUIRED if k not in pkg]
    checks.append(
        _check(
            "package has everything needed",
            not missing,
            f"missing: {', '.join(missing)}" if missing else "all required sections present",
        )
    )
    if missing:
        return {"passed": False, "checks": checks}
    c, run, result = pkg["concept"], pkg["run"], pkg["result"]

    ok, why = _ledger_chain(pkg["ledger"])
    checks.append(_check("teaching ledger hash chain", ok, why))

    dom_hash = DomainManifest.from_canonical(pkg["domain"]).hash
    checks.append(
        _check(
            "domain hash matches the concept",
            dom_hash == c.get("domain_hash"),
            f"recomputed {dom_hash[:12]}…",
        )
    )

    head = pkg["ledger"][-1]["hash"] if pkg["ledger"] else "genesis"
    sealed = sha(
        {
            "rule": c["rule"],
            "input_schema": c["input_schema"],
            "preservation": c["preservation"],
            "domain": dom_hash,
            "ledger": head,
        }
    )
    checks.append(
        _check(
            "sealed concept hash recomputed",
            sealed == c["sealed_hash"],
            f"recomputed {sealed[:12]}… claimed {c['sealed_hash'][:12]}…",
        )
    )

    prog = pkg.get("binding_program")
    if prog is not None:
        checks.append(
            _check(
                "native program matches its hash",
                sha(json.loads(prog)) == result["binding"]["program_hash"],
                "program recomputed",
            )
        )
        checks.append(
            _check(
                "native program carries the sealed concept hash",
                result["binding"]["concept_hash"] == sealed,
                "binding is bound to this exact rule",
            )
        )

    # exact re-evaluation of the rule on the stated input, compared with what the engine reported
    try:
        sc = card_scene(run["width"], run["height"], 100, 100)
        expected = evaluate_rule(c["rule"], sc["objects"], sc["canvas"])
    except (RuleError, KeyError, ValueError) as e:
        checks.append(
            _check("rule re-evaluated exactly", False, f"could not evaluate: {str(e)[:100]}")
        )
        return {"passed": False, "checks": checks}
    obs = {b["id"]: b for b in pkg["observed_geometry"]}
    worst, bad = 0.0, []
    for key, g in expected.items():
        o = obs.get(key)
        if o is None:
            bad.append(f"{key}: missing from the observed geometry")
            continue
        d = max(
            abs(float(Fraction(g["x"])) - o["x"]),
            abs(float(Fraction(g["y"])) - o["y"]),
            abs(float(Fraction(g.get("w", o["w"]))) - o["w"]),
            abs(float(Fraction(g.get("h", o["h"]))) - o["h"]),
        )
        worst = max(worst, d)
        if d > NATIVE_TOL:
            bad.append(f"{key}: off by {d:.2f}px")
    geometry_ok = not bad
    checks.append(
        _finding(
            "layout versus the rule's exact result",
            (
                f"matches (largest difference {worst:.3f}px, tolerance {NATIVE_TOL}px)"
                if geometry_ok
                else "DOES NOT MATCH: " + "; ".join(bad)
            ),
        )
    )

    claimed = bool(result.get("verifier_passed"))
    checks.append(
        _check(
            "the package's pass/fail claim agrees with the recomputation",
            claimed == geometry_ok,
            f"claims {'pass' if claimed else 'FAIL'}, recomputation says {'pass' if geometry_ok else 'FAIL'}",
        )
    )

    st = pkg.get("stress_test")
    if st:
        checks.append(
            _check(
                "stress-test counts add up",
                st["passed"] + st["failed"] == st["tested"] and len(st["failures"]) <= st["failed"],
                f"{st['passed']} passed + {st['failed']} failed = {st['tested']} tested",
            )
        )
    try:
        assert_no_aggregate_confidence(pkg)
        checks.append(
            _check(
                "no merged confidence or 'verified' score anywhere", True, "four axes stay separate"
            )
        )
    except Exception as e:  # noqa: BLE001
        checks.append(
            _check("no merged confidence or 'verified' score anywhere", False, str(e)[:100])
        )
    return {"passed": all(x["passed"] for x in checks if x["passed"] is not None), "checks": checks}
