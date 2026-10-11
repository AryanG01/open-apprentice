"""Concrete interpreter vs Z3 translation agree on the supported subset (spec 12.5).
Exact rationals on both sides. Evidence about the translation only -- not native engines or intent."""

from fractions import Fraction as F

import pytest
import z3
from hypothesis import HealthCheck, given, settings, strategies as st

from open_apprentice.concepts.rules import RuleError, evaluate_rule
from open_apprentice.concepts.symbolic import Unsupported, compile_rule, make_inputs
from tests.fixtures_rules import (
    CLAMPED_MARGIN,
    PROP_MARGIN,
    CONST_MARGIN,
)

N = 3
FIELDS = ("x", "y", "w", "h")
fr = st.fractions(min_value=F(-50), max_value=F(600), max_denominator=12)
const = st.one_of(st.integers(-40, 40), fr.map(lambda f: {"rat": f"{f.numerator}/{f.denominator}"}))
nonzero_const = st.one_of(
    st.integers(1, 9), st.integers(-9, -1), st.just({"rat": "3/7"}), st.just({"rat": "-5/2"})
)
LETS = ["l0", "l1"]


def leaf():
    return st.one_of(
        const,
        st.builds(
            lambda i, f: {"op": "get", "args": [{"ref": f"objects.{i}"}, f]},
            st.integers(0, N - 1),
            st.sampled_from(FIELDS),
        ),
        st.sampled_from(["w", "h"]).map(lambda f: {"ref": f"canvas.{f}"}),
        st.sampled_from(LETS).map(lambda n: {"ref": f"locals.{n}"}),
    )


def num_expr():
    def ext(c):
        return st.one_of(
            st.builds(
                lambda o, a, b: {"op": o, "args": [a, b]}, st.sampled_from(["add", "sub"]), c, c
            ),
            st.builds(
                lambda a, k, left: {"op": "mul", "args": [a, k] if left else [k, a]},
                c,
                const,
                st.booleans(),
            ),
            st.builds(lambda a, k: {"op": "div", "args": [a, k]}, c, nonzero_const),
            st.builds(
                lambda o, a, b: {"op": o, "args": [a, b]}, st.sampled_from(["min", "max"]), c, c
            ),
        )

    return st.recursive(leaf(), ext, max_leaves=6)


def cond_expr():
    cmp_ = st.builds(
        lambda o, a, b: {"op": o, "args": [a, b]},
        st.sampled_from(["lt", "le", "gt", "ge", "eq", "ne"]),
        num_expr(),
        num_expr(),
    )
    return st.recursive(
        cmp_,
        lambda c: st.one_of(
            st.builds(lambda a, b: {"op": "and", "args": [a, b]}, c, c),
            st.builds(lambda a, b: {"op": "or", "args": [a, b]}, c, c),
            st.builds(lambda a: {"op": "not", "args": [a]}, c),
        ),
        max_leaves=3,
    )


def emit():
    obj = st.integers(0, N - 1).map(lambda i: {"ref": f"objects.{i}"})
    mv = st.builds(
        lambda t, x, y: {"op": "emit_target", "kind": "move_existing", "target": t, "x": x, "y": y},
        obj,
        num_expr(),
        num_expr(),
    )
    rs = st.builds(
        lambda t, w, h: {
            "op": "emit_target",
            "kind": "resize_existing",
            "target": t,
            "w": w,
            "h": h,
        },
        obj,
        num_expr(),
        num_expr(),
    )
    cl = st.builds(
        lambda p, s, x, y: {
            "op": "emit_target",
            "kind": "clone_place",
            "proto": p,
            "symbol": s,
            "x": x,
            "y": y,
        },
        obj,
        st.sampled_from(["s1", "s2"]),
        num_expr(),
        num_expr(),
    )
    return st.one_of(mv, rs, cl)


def rebind():
    return st.builds(
        lambda n, v: {"op": "let", "name": n, "value": v}, st.sampled_from(LETS), num_expr()
    )


def body():
    simple = st.one_of(emit(), rebind())
    iff = st.builds(
        lambda c, t, e: {"op": "if", "cond": c, "then": t, "else": e},
        cond_expr(),
        st.lists(simple, max_size=2),
        st.lists(simple, max_size=2),
    )
    loop = st.builds(
        lambda b: {
            "op": "for_each",
            "var": "o",
            "over": {"ref": "objects"},
            "index_var": "i",
            "body": b,
        },
        st.lists(
            st.one_of(
                st.builds(
                    lambda x: {
                        "op": "emit_target",
                        "kind": "move_existing",
                        "target": {"ref": "locals.o"},
                        "x": x,
                        "y": {"ref": "locals.i"},
                    },
                    num_expr(),
                ),
                rebind(),
            ),
            min_size=1,
            max_size=2,
        ),
    )
    init = [{"op": "let", "name": n, "value": 7} for n in LETS]
    return st.lists(st.one_of(simple, iff, loop), min_size=1, max_size=4).map(lambda b: init + b)


def geometry():
    return st.tuples(st.lists(st.tuples(*[fr] * 4), min_size=N, max_size=N), st.tuples(fr, fr))


def sym_value(expr, subst):
    if isinstance(expr, (F, bool)):
        return expr
    s = z3.simplify(z3.substitute(expr, *subst))
    if z3.is_true(s):
        return True
    if z3.is_false(s):
        return False
    assert z3.is_rational_value(s), s
    return F(s.as_fraction())


def tie_geometry():
    """Few distinct small values => comparisons often hit equality (strict vs non-strict boundaries)."""
    v = st.sampled_from([F(0), F(1), F(2), F(7), F(-7)])
    return st.tuples(st.lists(st.tuples(v, v, v, v), min_size=N, max_size=N), st.tuples(v, v))


@settings(
    max_examples=250,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(body(), geometry())
def test_symbolic_matches_concrete(rule, geom):
    _check_agreement(rule, geom)


@settings(
    max_examples=300,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(body(), tie_geometry())
def test_symbolic_matches_concrete_at_ties(rule, geom):
    _check_agreement(rule, geom)


def _check_agreement(rule, geom):
    rects, (cw, ch) = geom
    objs_c = [{"id": f"obj{i}", **dict(zip(FIELDS, r))} for i, r in enumerate(rects)]
    canvas_c = {"w": cw, "h": ch}
    objs_s, cv_s, _ = make_inputs(N)
    try:
        sym = compile_rule(rule, objs_s, cv_s)
    except Unsupported:
        return  # outside the subset: reported, never guessed
    conc = evaluate_rule(rule, objs_c, canvas_c)
    subst = []
    for o, c in zip(objs_s, objs_c):
        subst += [(o.fields[f], z3.RealVal(f"{c[f].numerator}/{c[f].denominator}")) for f in FIELDS]
    subst += [
        (cv_s[k], z3.RealVal(f"{canvas_c[k].numerator}/{canvas_c[k].denominator}"))
        for k in ("w", "h")
    ]
    for key in set(sym) | set(conc):
        defined = sym_value(sym[key]["defined"], subst) if key in sym else False
        assert defined == (key in conc), (key, rule)
        if defined:
            for f in FIELDS:
                assert sym_value(sym[key][f], subst) == conc[key][f], (key, f, rule)


# ---- explicit rejections (12.5 / 22.7): unsupported is reported, never approximated -------------
def _sym(rule, n=2):
    o, c, _ = make_inputs(n)
    return compile_rule(rule, o, c)


def test_variable_times_variable_is_unsupported():
    w = lambda i: {"op": "get", "args": [{"ref": f"objects.{i}"}, "w"]}
    rule = [
        {
            "op": "emit_target",
            "kind": "move_existing",
            "target": {"ref": "objects.0"},
            "x": {"op": "mul", "args": [w(0), w(1)]},
            "y": 0,
        }
    ]
    with pytest.raises(Unsupported):
        _sym(rule)
    evaluate_rule(
        rule,
        [{"id": "a", "x": 0, "y": 0, "w": 3, "h": 3}, {"id": "b", "x": 0, "y": 0, "w": 4, "h": 4}],
        {"w": 99, "h": 99},
    )  # concrete still runs


def test_variable_divisor_is_unsupported():
    w = lambda i: {"op": "get", "args": [{"ref": f"objects.{i}"}, "w"]}
    rule = [
        {
            "op": "emit_target",
            "kind": "move_existing",
            "target": {"ref": "objects.0"},
            "x": {"op": "div", "args": [w(0), w(1)]},
            "y": 0,
        }
    ]
    with pytest.raises(Unsupported):
        _sym(rule)


def test_floats_rejected_by_both():
    rule = [{"op": "let", "name": "a", "value": 0.1}]
    with pytest.raises(RuleError):
        _sym(rule)
    with pytest.raises(RuleError):
        evaluate_rule(rule, [{"id": "a", "x": 0, "y": 0, "w": 3, "h": 3}], {"w": 9, "h": 9})


def test_boundary_of_clamp_agrees_exactly():
    """Branch boundary: 8% of w == 8 at w=100 and == 24 at w=300 (min/max edges)."""
    for rule in (CLAMPED_MARGIN(), PROP_MARGIN(), CONST_MARGIN):
        for w in (99, 100, 101, 299, 300, 301):
            objs_c = [
                {"id": "obj0", "x": 10, "y": 10, "w": w, "h": 50},
                {"id": "obj1", "x": 0, "y": 0, "w": 20, "h": 20},
            ]
            conc = evaluate_rule(rule, objs_c, {"w": 800, "h": 600})["badge"]
            o, c, _ = make_inputs(2)
            sym = compile_rule(rule, o, c)["badge"]
            subst = [(o[i].fields[f], z3.RealVal(objs_c[i][f])) for i in range(2) for f in FIELDS]
            assert (
                sym_value(sym["x"], subst) == conc["x"] and sym_value(sym["y"], subst) == conc["y"]
            )
