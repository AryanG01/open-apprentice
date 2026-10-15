from fractions import Fraction as F

import pytest

from open_apprentice.teaching.teacher import (
    ChooseOutput,
    ConfirmPreview,
    ProtocolError,
    RequestDemonstration,
    Response,
    max_error,
    request_from_json,
    request_to_json,
    validate_request,
    validate_response,
)

REG = {"s1": "h1"}


def test_max_error():
    assert max_error({"l": (F(0), F(0))}, {"l": (F(1, 4), F(-1, 2))}) == F(1, 2)
    assert max_error({"l": (F(0), F(0))}, {"m": (F(0), F(0))}) is None


def test_choose_requires_2_to_4_separated_alternatives():
    a = ("A", {"l": (F(0), F(0))})
    b = ("B", {"l": (F(3, 4), F(0))})  # only 0.75 apart: both could match a truth at 0.375
    with pytest.raises(ProtocolError):
        validate_request(ChooseOutput("q1", "s1", "h1", (a, b)), REG)
    c = ("C", {"l": (F(2), F(0))})
    validate_request(ChooseOutput("q1", "s1", "h1", (a, c)), REG)
    with pytest.raises(ProtocolError):
        validate_request(ChooseOutput("q1", "s1", "h1", (a,)), REG)


def test_unregistered_or_mismatched_scene_is_protocol_error():
    a, c = ("A", {"l": (F(0), F(0))}), ("C", {"l": (F(2), F(0))})
    with pytest.raises(ProtocolError):
        validate_request(ChooseOutput("q1", "s9", "h1", (a, c)), REG)
    with pytest.raises(ProtocolError):
        validate_request(RequestDemonstration("q2", "s1", "WRONG"), REG)


def test_preview_item_limits_and_per_item_response():
    out = {"l": (F(0), F(0))}
    items = tuple((f"i{k}", "s1", "h1", out) for k in range(4))
    with pytest.raises(ProtocolError):
        validate_request(ConfirmPreview("p1", "learning_preview", items), REG)
    req = ConfirmPreview("p1", "learning_preview", items[:2])
    validate_request(req, REG)
    validate_response(req, Response("p1", "items", per_item=(("i0", "approve"), ("i1", "unsure"))))
    with pytest.raises(ProtocolError):
        validate_response(req, Response("p1", "items", per_item=(("i0", "approve"),)))


def test_choose_response_must_name_a_shown_alternative():
    a, c = ("A", {"l": (F(0), F(0))}), ("C", {"l": (F(2), F(0))})
    req = ChooseOutput("q1", "s1", "h1", (a, c))
    validate_response(req, Response("q1", "choose", selected="C"))
    validate_response(req, Response("q1", "none"))
    with pytest.raises(ProtocolError):
        validate_response(req, Response("q1", "choose", selected="Z"))


def test_json_round_trip():
    req = ChooseOutput(
        "q1", "s1", "h1", (("A", {"l": (F(1, 3), F(0))}), ("C", {"l": (F(2), F(0))}))
    )
    assert request_from_json(request_to_json(req)) == req
