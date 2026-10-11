import json

import httpx
import pytest

from open_apprentice.config import Settings
from open_apprentice.providers.capabilities import run_probe

KEY = "sk-live-SECRET-1234567890"
MODEL = "nvidia/nemotron-3-super-120b-a12b"


def settings():
    return Settings(
        nebius_base_url="https://x.test/v1/",
        nebius_model=MODEL,
        provider_mode="nebius",
        live_run_max_usd="1",
        _raw_env={"NEBIUS_API_KEY": KEY},
    )


def ok_chat(content="ok", model=MODEL, finish="stop", usage=True, extra_msg=None):
    body = {
        "id": "req-9",
        "model": model,
        "choices": [
            {"message": {"content": content, **(extra_msg or {})}, "finish_reason": finish}
        ],
    }
    if usage:
        body["usage"] = {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13}
    return httpx.Response(200, json=body)


def server(
    *, schema_ok=True, json_ok=True, reject_max_tokens=False, listed=True, status_models=200
):
    seen = []

    def h(req: httpx.Request):
        seen.append((req.method, req.url.path, json.loads(req.content) if req.content else None))
        assert req.headers["authorization"] == f"Bearer {KEY}"
        if req.url.path.endswith("/models"):
            if status_models != 200:
                return httpx.Response(status_models, json={"error": {"message": f"bad key {KEY}"}})
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": MODEL if listed else "other/model"},
                        {"id": "some/nemotron-nano"},
                    ]
                },
            )
        b = json.loads(req.content)
        if reject_max_tokens and "max_tokens" in b:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "max_tokens is not supported; use max_completion_tokens",
                        "type": "invalid_request_error",
                    }
                },
            )
        rf = (b.get("response_format") or {}).get("type")
        if rf == "json_schema":
            return (
                ok_chat('{"answer": 7}')
                if schema_ok
                else httpx.Response(
                    400,
                    json={
                        "error": {
                            "message": "json_schema unsupported",
                            "type": "invalid_request_error",
                        }
                    },
                )
            )
        if rf == "json_object":
            return ok_chat('{"answer": 7}' if json_ok else "sure! the answer is 7")
        return ok_chat()

    return h, seen


async def go(handler, **kw):
    return await run_probe(settings(), transport=httpx.MockTransport(handler), **kw)


async def test_happy_path_records_accepted_options_and_never_leaks_the_key():
    h, seen = server()
    rep = await go(h)
    s = rep["summary"]
    assert (
        s["authenticated"]
        and s["model_identity_matches_request"]
        and s["recommended_json_mode"] == "json_schema"
        and s["usage_reported"]
    )
    ao = rep["accepted_options"]
    assert {k: ao[k] for k in ("completion_limit_field", "json_object", "json_schema", "seed")} == {
        "completion_limit_field": "max_tokens",
        "json_object": True,
        "json_schema": True,
        "seed": True,
    }
    assert ao["reasoning_effort"]["low"]["accepted"] and ao["reasoning_effort"]["none"]["accepted"]
    assert rep["usage_fields_seen"] == [
        "completion_tokens",
        "prompt_tokens",
        "total_tokens",
    ] and rep["returned_model_ids"] == [MODEL]
    assert KEY not in json.dumps(rep) and KEY not in repr(seen)[:0] + json.dumps(rep)
    assert rep["calls_made"] <= 8


async def test_schema_rejection_falls_back_to_json_object_and_is_recorded_not_hidden():
    h, _ = server(schema_ok=False)
    rep = await go(h)
    assert (
        rep["accepted_options"]["json_schema"] is False
        and rep["summary"]["recommended_json_mode"] == "json_object"
    )
    failing = [c for c in rep["checks"] if c["name"] == "json_schema"][0]
    assert failing["ok"] is False and "unsupported" in failing["message"]


async def test_truncated_schema_output_is_INCONCLUSIVE_not_a_rejection_and_reasoning_is_recorded():
    """A reasoning model can spend its whole completion budget thinking: 'length' + empty content must not be read as
    'json_schema unsupported'."""

    def h(req):
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": MODEL}]})
        b = json.loads(req.content)
        if (b.get("response_format") or {}).get("type") == "json_schema":
            return ok_chat("", finish="length", extra_msg={"reasoning_content": "thinking..."})
        if b.get("max_tokens") == 32:
            return ok_chat("", finish="length", extra_msg={"reasoning_content": "thinking..."})
        return ok_chat('{"answer": 7}' if b.get("response_format") else "ok")

    rep = await go(h)
    sc = [c for c in rep["checks"] if c["name"] == "json_schema"][0]
    assert (
        sc["status"] == "inconclusive_truncated"
        and rep["summary"]["json_schema_status"] == "inconclusive_truncated"
    )
    small = [c for c in rep["checks"] if c["name"] == "small_cap_behaviour"][0]
    assert (
        small["visible_content_chars"] == 0
        and small["reasoning_fields_present"] == ["reasoning_content"]
        and rep["reasoning_model_detected"] is True
    )


async def test_json_object_mode_that_returns_prose_is_not_accepted():
    h, _ = server(schema_ok=False, json_ok=False)
    rep = await go(h)
    assert (
        rep["accepted_options"]["json_object"] is False
        and rep["summary"]["recommended_json_mode"] == "prompt_only"
    )


async def test_limit_field_fallback_to_max_completion_tokens():
    h, seen = server(reject_max_tokens=True)
    rep = await go(h)
    assert rep["accepted_options"]["completion_limit_field"] == "max_completion_tokens"
    assert any(b and "max_completion_tokens" in b for _, _, b in seen)


async def test_auth_failure_stops_immediately_with_no_further_requests_and_redacts_the_body():
    h, seen = server(status_models=401)
    rep = await go(h)
    assert (
        "authentication failed" in rep["aborted"] and len(seen) == 1 and KEY not in json.dumps(rep)
    )
    assert rep["summary"]["authenticated"] is False


async def test_a_model_not_in_the_listing_or_returned_under_another_name_is_not_a_pass():
    h, _ = server(listed=False)
    rep = await go(h)
    assert [c for c in rep["checks"] if c["name"] == "list_models"][0][
        "requested_model_listed"
    ] is False

    def other(req):
        return (
            ok_chat(model="some/other-model")
            if "chat" in req.url.path
            else httpx.Response(200, json={"data": []})
        )

    rep2 = await go(other)
    assert rep2["summary"]["model_identity_matches_request"] is False


async def test_hard_call_cap_and_token_ceiling():
    h, seen = server()
    rep = await go(h, max_calls=3)
    assert len(seen) == 3 and "call cap" in rep["aborted"]
    h2, seen2 = server()
    rep2 = await go(h2, max_total_tokens=5)  # first chat call already exceeds it
    assert "token ceiling" in rep2["aborted"] and len(seen2) <= 3


async def test_missing_key_aborts_before_any_network():
    from open_apprentice.providers.capabilities import ProbeAborted

    with pytest.raises(ProbeAborted):
        await run_probe(
            Settings(_raw_env={}),
            transport=httpx.MockTransport(lambda r: pytest.fail("must not send")),
        )


async def test_reasoning_effort_is_probed_and_rejection_is_recorded_not_fatal():
    def h(req):
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": MODEL}]})
        b = json.loads(req.content)
        if b.get("reasoning_effort") == "none":
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "reasoning_effort none unsupported",
                        "type": "invalid_request_error",
                    }
                },
            )
        return ok_chat('{"answer": 7}' if b.get("response_format") else "ok")

    rep = await go(h)
    e = rep["accepted_options"]["reasoning_effort"]
    assert (
        e["low"]["accepted"] is True and e["none"]["accepted"] is False and rep["calls_made"] <= 8
    )
