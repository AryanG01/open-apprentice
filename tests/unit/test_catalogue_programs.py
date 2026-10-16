from fractions import Fraction as F

from open_apprentice.concepts.catalogue_programs import CATALOGUE, CatalogueProposer
from open_apprentice.concepts.label_teaching import describe_compact
from open_apprentice.concepts.rules import evaluate_rule
from open_apprentice.evaluation.label_episodes import CATALOGUE as SPECS
from open_apprentice.evaluation.label_episodes import PROBES
from open_apprentice.evaluation.labels import apply_oracle, rule_for_spec
from open_apprentice.evaluation.specs_v2 import VSpec, oracle_v, scene_v
from open_apprentice.teaching import codec
from open_apprentice.concepts.hypotheses import Constraint


def _name(s):
    return f"{s.primary}/{s.fallback or 'none'}/{s.scope}/{s.gap}"


def _run(rule, scene):
    st = evaluate_rule(rule, scene["objects"], scene["canvas"])
    return {k: (v["x"], v["y"]) for k, v in st.items()}


def test_twenty_four_distinct_named_programs():
    assert len(CATALOGUE) == 24
    assert len({n for n, _ in CATALOGUE}) == 24
    assert len({codec.digest(r) for _, r in CATALOGUE}) == 24
    assert {n for n, _ in CATALOGUE} == {_name(s) for s in SPECS}


def test_each_program_behaves_like_the_evaluator_reference_on_the_probe_pool():
    by_name = dict(CATALOGUE)
    for spec in SPECS:
        mine, ref = by_name[_name(spec)], rule_for_spec(spec)
        for scene in PROBES:
            assert _run(mine, scene) == _run(ref, scene), (_name(spec), scene["objects"][0])


def _evidence(spec, scenes):
    cs = []
    for i, s in enumerate(scenes):
        after = apply_oracle(s, oracle_v(spec, s))
        expected = {
            o["id"]: {"x": F(o["x"]), "y": F(o["y"])}
            for o in after["objects"]
            if o["kind"] == "label"
        }
        cs.append(Constraint("positive", s, expected, source="demonstration"))
    return {"teaching_evidence": describe_compact(cs)}


def test_proposer_returns_every_fitting_catalogue_program():
    spec = SPECS[0]
    scenes = [scene_v("grid", 3)]
    cands, usage, cost = CatalogueProposer().propose(
        _evidence(VSpec("catalogue", (spec,)), scenes), "initial", ()
    )
    names = {c["summary"] for c in cands}
    assert _name(spec) in names and cost == 0 and usage["source"] == "catalogue"
    for c in cands:
        assert _run(c["rule"], scenes[0]) == _run(rule_for_spec(spec), scenes[0])


def test_beyond_catalogue_evidence_gets_no_candidates():
    scenes = [scene_v("rows", 5), scene_v("columns", 6)]
    cands, _, _ = CatalogueProposer().propose(
        _evidence(VSpec("gap_by_width", ()), scenes), "initial", ()
    )
    assert cands == []
