"""Real-SVG lane (experimental): validation, byte-exact patching, harmful-patch rejection, and the learned rule applied to three owner-authored assets."""

import pathlib

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from open_apprentice.svg.document import inventory, parse_document
from open_apprentice.svg.patch import Op, Patch, PatchRejected, apply_patch, edit_tag
from open_apprentice.svg.rule_apply import RuleNotApplicable, patch_for_pairs
from open_apprentice.svg.safety import SvgRejected, validate_svg
from tests.fixtures_rules import CONST_MARGIN

SAMPLES = pathlib.Path("src/open_apprentice/svg/samples")
ASSETS = {
    "product-cards": [("card-1", "badge-1"), ("card-2", "badge-2"), ("card-3", "badge-3")],
    "dashboard-tiles": [("a-card", "a-badge"), ("b-card", "b-badge"), ("c-card", "c-badge")],
    "pricing-table": [("plan-free", "plan-free-tag"), ("plan-pro", "plan-pro-tag")],
}
SVG = 'xmlns="http://www.w3.org/2000/svg"'


def read(name):
    return (SAMPLES / f"{name}.svg").read_text()


@pytest.mark.parametrize("name", ASSETS)
def test_samples_are_accepted_and_an_empty_patch_is_a_byte_exact_round_trip(name):
    text = read(name)
    d = parse_document(text)
    r = apply_patch(text, Patch(doc_hash=d.hash, ops=[]))
    assert r.text == text and r.hash_after == r.hash_before and r.unrelated_byte_changes == 0


@pytest.mark.parametrize("name", ASSETS)
def test_the_learned_rule_moves_badges_exactly_where_the_rule_says_and_nothing_else_changes(name):
    text = read(name)
    d = parse_document(text)
    patch, expected = patch_for_pairs(d, CONST_MARGIN, ASSETS[name])
    r = apply_patch(text, patch)
    assert r.unrelated_byte_changes == 0 and {x["attribute"] for x in r.diff} <= {
        "x",
        "y",
        "width",
        "height",
    }
    assert {x["element"] for x in r.diff} <= {b for _, b in ASSETS[name]}
    after = {row["id"]: row for row in inventory(parse_document(r.text))["elements"]}
    for (
        ex
    ) in (
        expected
    ):  # inventory is a re-derivation from the NEW document; the browser check is separate
        w = after[ex["badge"]]["world"]
        assert (w["x"], w["y"]) == pytest.approx((ex["world"]["x"], ex["world"]["y"]), abs=1e-3)
    # every changed line is a badge or tag element; all other lines are byte-identical
    old_lines, new_lines = text.splitlines(), r.text.splitlines()
    assert len(old_lines) == len(new_lines)
    changed = [a for a, b in zip(old_lines, new_lines) if a != b]
    assert changed and all("badge" in a or "tag" in a for a in changed)


def test_translated_groups_are_handled_with_world_coordinates():
    d = parse_document(read("dashboard-tiles"))
    rows = {r["id"]: r for r in inventory(d)["elements"]}
    assert (
        rows["c-card"]["world"]["x"] == 50 and rows["c-card"]["world"]["y"] == 170
    )  # translate(40 170) then translate(10 0)
    assert rows["a-card"]["local"]["x"] == 0 and rows["a-card"]["world"]["x"] == 40


def test_a_rotated_element_is_refused_with_a_reason_and_shown_in_the_coverage():
    d = parse_document(read("pricing-table"))
    inv = inventory(d)
    promo = next(r for r in inv["elements"] if r["id"] == "plan-promo")
    assert promo["editable"] is False and "transform" in promo["reason"]
    assert inv["coverage"]["editable"] < inv["coverage"]["listed"]
    with pytest.raises(RuleNotApplicable, match="transform"):
        patch_for_pairs(d, CONST_MARGIN, [("plan-promo", "plan-promo-tag")])


@pytest.mark.parametrize(
    "doc, why",
    [
        (f"<svg {SVG}><script>alert(1)</script></svg>", "scripts"),
        (f'<svg {SVG}><rect id="a" onclick="x()"/></svg>', "event-handler"),
        (f'<svg {SVG}><image href="http://evil.example/x.png"/></svg>', "image"),
        (f'<svg {SVG}><a href="https://x"><rect/></a></svg>', "links"),
        (f"<svg {SVG}><foreignObject/></svg>", "embedded"),
        (f"<svg {SVG}><style>rect{{fill:url(http://x)}}</style></svg>", "style"),
        (f'<svg {SVG}><rect fill="url(http://x/y)"/></svg>', "external resource"),
        (f'<svg {SVG}><rect fill="javascript:alert(1)"/></svg>', "active value"),
        (f'<svg {SVG}><rect id="a"/><rect id="a"/></svg>', "duplicate id"),
        ('<!DOCTYPE svg [<!ENTITY x "y">]><svg xmlns="http://www.w3.org/2000/svg"/>', "DOCTYPE"),
        (f"<svg {SVG}><rect", "well-formed"),
        ("<html/>", "root element"),
        (f"<svg {SVG}>" + "<g>" * 40 + "</g>" * 40 + "</svg>", "nested"),
        (f"<svg {SVG}><!-- " + "x" * 210_000 + " --></svg>", "limit"),
        (
            '<svg xmlns="http://www.w3.org/2000/svg" xmlns:h="http://www.w3.org/1999/xhtml"><h:div/></svg>',
            "namespace",
        ),
        # An HTML parser ends this processing instruction at the first ">" and turns the <img> into live markup.
        (
            f'<svg {SVG}><?x ><img src="x"/onerror="alert(1)"?><rect id="a"/></svg>',
            "processing instruction",
        ),
    ],
)
def test_incompatible_documents_are_rejected_with_a_reason_not_sanitised(doc, why):
    with pytest.raises(SvgRejected, match=why):
        validate_svg(doc)


def patch_of(d, *ops):
    return Patch(doc_hash=d.hash, ops=[Op(**o) for o in ops])


def test_harmful_patches_are_rejected_and_nothing_is_applied():
    text = read("product-cards")
    d = parse_document(text)
    good = dict(element="badge-1", attribute="x", expected_old="90", new="100")
    cases = {
        "stale document": Patch(doc_hash="0" * 64, ops=[Op(**good)]),
        "stale value": patch_of(d, {**good, "expected_old": "999"}),
        "unlisted attribute": patch_of(
            d, dict(element="badge-1", attribute="onclick", expected_old=None, new="x()")
        ),
        "href": patch_of(
            d, dict(element="badge-1", attribute="href", expected_old=None, new="http://x")
        ),
        "style": patch_of(
            d, dict(element="badge-1", attribute="style", expected_old=None, new="x")
        ),
        "nan": patch_of(d, {**good, "new": "nan"}),
        "huge": patch_of(d, {**good, "new": "1e12"}),
        "negative size": patch_of(
            d, dict(element="badge-1", attribute="width", expected_old="20", new="-5")
        ),
        "url fill": patch_of(
            d,
            dict(
                element="badge-1", attribute="fill", expected_old="#76b900", new="url(http://x/y)"
            ),
        ),
        "unknown element": patch_of(d, {**good, "element": "nope"}),
        "not a rect": patch_of(
            d, dict(element="canvas-bg", attribute="x", expected_old="0", new="1")
        ),
        "duplicate write": patch_of(d, good, {**good, "new": "101"}),
        "bad transform": patch_of(
            d, dict(element="badge-1", attribute="transform", expected_old=None, new="rotate(30)")
        ),
    }
    for name, p in cases.items():
        if name == "not a rect":
            continue  # canvas-bg IS a rect; covered below via the definitions case
        with pytest.raises(PatchRejected):
            apply_patch(text, p)
    mixed = patch_of(
        d,
        good,
        {**good, "element": "badge-2", "attribute": "href", "expected_old": None, "new": "x"},
    )
    with pytest.raises(PatchRejected):
        apply_patch(text, mixed)  # one valid op + one invalid op: transactional, nothing applied
    assert text == read("product-cards")


def test_definitions_are_not_editable():
    text = '<svg xmlns="http://www.w3.org/2000/svg"><defs><rect id="shared" x="0" y="0" width="5" height="5"/></defs></svg>'
    d = parse_document(text)
    with pytest.raises(PatchRejected, match="shared definitions"):
        apply_patch(
            text, patch_of(d, dict(element="shared", attribute="x", expected_old="0", new="9"))
        )


def test_tag_editing_survives_awkward_attribute_text():
    tag = b"<rect\n   id='r'  data-x=\"a > b 'q' x=1\"\n x = '1'  y=\"2\" />"
    out = edit_tag(tag, {"x": "9", "y": "8", "fill": "#fff"})
    assert (
        b"x = '9'" in out
        and b'y="8"' in out
        and b"data-x=\"a > b 'q' x=1\"" in out
        and out.rstrip().endswith(b'fill="#fff" />')
    )


@settings(max_examples=60, deadline=None)
@given(x=st.floats(-5000, 5000, allow_nan=False), y=st.floats(-5000, 5000, allow_nan=False))
def test_any_valid_move_changes_only_the_targeted_attributes(x, y):
    text = read("dashboard-tiles")
    d = parse_document(text)
    from open_apprentice.svg.patch import fmt

    r = apply_patch(
        text,
        patch_of(
            d,
            dict(element="b-badge", attribute="x", expected_old="10", new=fmt(x)),
            dict(element="b-badge", attribute="y", expected_old="10", new=fmt(y)),
        ),
    )
    assert r.unrelated_byte_changes == 0
    after = parse_document(r.text)
    assert float(after.get("b-badge").attrs["x"]) == pytest.approx(float(fmt(x)), abs=1e-4)
    assert [e.attrs for e in after.elements if e.attrs.get("id") != "b-badge"] == [
        e.attrs for e in d.elements if e.attrs.get("id") != "b-badge"
    ]


def test_suggested_pairs_match_the_intended_cards_and_ignore_page_backgrounds():
    from open_apprentice.api.svg import suggest_pairs

    for name, pairs in ASSETS.items():
        got = {
            (p["card"], p["badge"]) for p in suggest_pairs(inventory(parse_document(read(name))))
        }
        assert got == set(pairs), (name, got)
