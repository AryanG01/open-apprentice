"""The 'watch it think' trace: what the apprentice considered, recomputed from the session's own events."""

from tests.unit.api_v2.conftest import answer_until_done, start_session


def test_trace_shows_rounds_question_and_commit(client, v2, doc_bytes, batch_bytes):
    sid = start_session(client, v2, doc_bytes, batch_bytes, key="think")
    s = client.get(f"/api/v2/sessions/{sid}").json()
    t = s["thinking"]
    assert t[0]["kind"] == "round" and t[0]["source"] == "offline enumerator"
    assert t[0]["proposed"] >= t[0]["survivors"] >= 1
    q = next((x for x in t if x["kind"] == "question"), None)
    if q is not None:  # a question was needed: its groups name the alternatives it shows
        alts = {a for a, _ in s["outstanding"]["request"]["alternatives"]}
        assert set(q["groups"]) == alts and all(q["groups"].values())
    done = answer_until_done(client, v2, sid)
    t2 = done["thinking"]
    assert t2[-1]["kind"] == "commit" and t2[-1]["summary"]
    assert client.get(f"/api/v2/sessions/{sid}").json()["thinking"] == t2  # deterministic


def test_trace_names_the_rules_behind_each_alternative_of_a_probe_question(client, v2, doc_bytes):
    from tests.unit.api_v2.test_probes_api import BATCH, TwoRules

    v2.proposer = TwoRules()
    sid = start_session(client, v2, doc_bytes, BATCH, key="think-probe")
    s = client.get(f"/api/v2/sessions/{sid}").json()
    t = s["thinking"]
    assert (
        t[0]["proposed"] == 2 and t[0]["survivors"] == 2 and t[0]["source"] == "offline enumerator"
    )
    assert any(x["kind"] == "probe" and x["ok"] for x in t)
    q = next(x for x in t if x["kind"] == "question")
    assert sorted(sum(q["groups"].values(), [])) == ["right", "x + 112"]
    assert set(q["groups"]) == {a for a, _ in s["outstanding"]["request"]["alternatives"]}
