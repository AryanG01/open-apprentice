from open_apprentice.evaluation.campaign_parity import parity_table, render_markdown

from .conftest import TOKEN


def test_parity_table_covers_every_gold_on_both_backends(engine_url):
    t = parity_table(engine_url, TOKEN)
    rows = t["verifier_rows"]
    assert len(rows) == 16  # 8 applicable gold outcomes x 2 backends
    assert {r["backend"] for r in rows} == {"konva", "fabric"}
    assert all(r["passed"] for r in rows), [r for r in rows if not r["passed"]]
    assert len(t["rule_sha256"]) == 64
    statuses = {(r["fixture"], r["backend"]): r["status"] for r in t["run_rows"]}
    for b in ("konva", "fabric"):
        assert statuses[("short_a", b)] == "ready" and statuses[("de_long_a", b)] == "question"
        assert statuses[("missing_role", b)] == "needs_roles"
    md = render_markdown(t)
    assert "development fixtures, not held out" in md and "| de_long_b | split | fabric |" in md
