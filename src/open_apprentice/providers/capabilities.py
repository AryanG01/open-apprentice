"""Live capability probe for the Nebius Token Factory endpoint (spec 14.3).

Resolves what the docs leave open (model id, JSON-object vs json_schema, the completion-limit field, usage fields,
seed support) by asking the REAL endpoint. A failed probe is an integration fact, never a model-reasoning failure.

Spend control without known rates: a hard call cap and a hard total-token ceiling (documented conservative
reservation, spec 19.3). The API key is never printed, logged, or written: every string leaving this module is
scrubbed of it.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from open_apprentice.config import Settings

MAX_CALLS = 8
MAX_TOTAL_TOKENS = (
    6000  # raised from 3000: Nemotron is a reasoning model and spends hidden tokens (measured)
)


class ProbeAborted(Exception):
    pass


def _scrub(text: Any, key: str, limit: int = 300) -> str:
    t = str(text)
    if key:
        t = t.replace(key, "<redacted>")
    return t[:limit]


def _err(r: httpx.Response, key: str) -> dict:
    try:
        e = r.json().get("error", r.json())
        e = {
            k: _scrub(v, key, 200)
            for k, v in (e.items() if isinstance(e, dict) else [("message", e)])
            if k in ("message", "type", "code", "param")
        }
    except Exception:
        e = {"message": _scrub(r.text, key)}
    return {"http_status": r.status_code, **e}


class _Budget:
    def __init__(self, max_calls: int, max_tokens: int) -> None:
        self.calls, self.tokens, self.max_calls, self.max_tokens = 0, 0, max_calls, max_tokens

    def before_call(self) -> None:
        if self.calls >= self.max_calls:
            raise ProbeAborted(f"call cap {self.max_calls} reached")
        if self.tokens >= self.max_tokens:
            raise ProbeAborted(f"token ceiling {self.max_tokens} reached")
        self.calls += 1


async def run_probe(
    settings: Settings,
    *,
    max_calls: int = MAX_CALLS,
    max_total_tokens: int = MAX_TOTAL_TOKENS,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> dict:
    key = settings._raw_env.get("NEBIUS_API_KEY", "")
    if not key:
        raise ProbeAborted("NEBIUS_API_KEY is not set")
    base = settings.nebius_base_url.rstrip("/")
    model = settings.nebius_model
    budget = _Budget(max_calls, max_total_tokens)
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    report: dict[str, Any] = {
        "probed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base_url": base + "/",
        "requested_model": model,
        "checks": [],
        "accepted_options": {},
        "usage_fields_seen": [],
        "returned_model_ids": [],
        "limits": {"max_calls": max_calls, "max_total_tokens": max_total_tokens},
        "cost_note": "dollar cost not computed: rates are only used when INPUT/OUTPUT_USD_PER_MILLION are configured",
    }
    usage_keys: set[str] = set()
    returned: set[str] = set()

    def record(name: str, ok: bool, **detail: Any) -> dict:
        c = {"name": name, "ok": ok, **detail}
        report["checks"].append(c)
        return c

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(60.0, connect=10.0), transport=transport
    ) as client:

        async def chat(body: dict) -> tuple[Optional[dict], dict, httpx.Response]:
            budget.before_call()
            t0 = time.perf_counter()
            r = await client.post(
                base + "/chat/completions", json={"model": model, **body}, headers=headers
            )
            meta = {
                "latency_ms": round((time.perf_counter() - t0) * 1000),
                "http_status": r.status_code,
                "request_id": r.headers.get("x-request-id"),
            }
            data = None
            if r.status_code == 200:
                data = r.json()
                meta["request_id"] = meta["request_id"] or data.get("id")
                u = data.get("usage") or {}
                usage_keys.update(u.keys())
                budget.tokens += int(
                    u.get("total_tokens")
                    or (u.get("prompt_tokens", 0) + u.get("completion_tokens", 0))
                    or 200
                )
                if data.get("model"):
                    returned.add(data["model"])
                meta["usage"] = {k: v for k, v in u.items() if isinstance(v, (int, float))}
                det = u.get("completion_tokens_details")
                if isinstance(det, dict):
                    meta["completion_tokens_details"] = {
                        k: v for k, v in det.items() if isinstance(v, (int, float))
                    }
            return data, meta, r

        try:
            # 1) model listing (documented /models endpoint)
            budget.before_call()
            r = await client.get(base + "/models", headers=headers)
            if r.status_code == 200:
                ids = [m.get("id") for m in (r.json().get("data") or []) if isinstance(m, dict)]
                record(
                    "list_models",
                    True,
                    http_status=200,
                    model_count=len(ids),
                    requested_model_listed=model in ids,
                    nemotron_models=sorted(i for i in ids if i and "nemotron" in i.lower())[:20],
                )
            else:
                record("list_models", False, **_err(r, key))
                if r.status_code in (401, 403):
                    raise ProbeAborted("authentication failed; stopping without further requests")

            # 2) completion-limit field + reasoning behaviour. Small cap first (informative), then a realistic one.
            limit_field = None
            for field in ("max_tokens", "max_completion_tokens"):
                data, meta, r = await chat(
                    {"messages": [{"role": "user", "content": "Reply with exactly: ok"}], field: 32}
                )
                if data is not None:
                    limit_field = field
                    ch = data["choices"][0]
                    msg = ch["message"]
                    record(
                        "small_cap_behaviour",
                        True,
                        limit_field=field,
                        cap=32,
                        finish_reason=ch.get("finish_reason"),
                        visible_content_chars=len(msg.get("content") or ""),
                        message_fields=sorted(msg.keys()),
                        reasoning_fields_present=[k for k in msg if "reason" in k and msg.get(k)],
                        **meta,
                    )
                    report["reasoning_model_detected"] = bool(
                        [k for k in msg if "reason" in k and msg.get(k)]
                    ) or (ch.get("finish_reason") == "length" and not (msg.get("content") or ""))
                    break
                record(f"small_cap_behaviour[{field}]", False, **{**meta, **_err(r, key)})
                if r.status_code in (401, 403):
                    raise ProbeAborted("authentication failed; stopping")
            report["accepted_options"]["completion_limit_field"] = limit_field
            if limit_field is None:
                raise ProbeAborted("no completion-limit field was accepted")
            data, meta, r = await chat(
                {
                    "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
                    limit_field: 512,
                }
            )
            if data is not None:
                ch = data["choices"][0]
                record(
                    "minimal_completion",
                    bool((ch["message"].get("content") or "").strip()),
                    cap=512,
                    finish_reason=ch.get("finish_reason"),
                    visible_content_chars=len(ch["message"].get("content") or ""),
                    returned_model=data.get("model"),
                    **meta,
                )
            else:
                record("minimal_completion", False, **{**meta, **_err(r, key)})
            lim = {limit_field: 768}

            # 3) JSON-object mode + local validation
            data, meta, r = await chat(
                {
                    "messages": [
                        {"role": "user", "content": 'Return only a JSON object {"answer": 7}.'}
                    ],
                    "response_format": {"type": "json_object"},
                    **lim,
                }
            )
            if data is not None:
                txt = data["choices"][0]["message"].get("content") or ""
                try:
                    parsed = json.loads(txt)
                    ok = isinstance(parsed, dict) and isinstance(parsed.get("answer"), int)
                except ValueError:
                    ok = False
                fr = data["choices"][0].get("finish_reason")
                record(
                    "json_object",
                    ok,
                    parsed_ok=ok,
                    finish_reason=fr,
                    status=(
                        "ok"
                        if ok
                        else "inconclusive_truncated" if fr == "length" else "rejected_output"
                    ),
                    **meta,
                )
                report["accepted_options"]["json_object"] = bool(ok)
            else:
                record("json_object", False, **{**meta, **_err(r, key)})
                report["accepted_options"]["json_object"] = False

            # 3b) documented reasoning_effort: is it accepted, and does it change hidden reasoning spend?
            efforts: dict[str, Any] = {}
            for effort in ("low", "none"):
                data, meta, r = await chat(
                    {
                        "messages": [
                            {"role": "user", "content": 'Return only a JSON object {"answer": 7}.'}
                        ],
                        "response_format": {"type": "json_object"},
                        "reasoning_effort": effort,
                        **lim,
                    }
                )
                if data is not None:
                    txt = data["choices"][0]["message"].get("content") or ""
                    try:
                        ok = isinstance(json.loads(txt).get("answer"), int)
                    except (ValueError, AttributeError):
                        ok = False
                    rt = (meta.get("completion_tokens_details") or {}).get("reasoning_tokens")
                    record(
                        f"reasoning_effort={effort}",
                        ok,
                        parsed_ok=ok,
                        reasoning_tokens=rt,
                        finish_reason=data["choices"][0].get("finish_reason"),
                        **meta,
                    )
                    efforts[effort] = {
                        "accepted": True,
                        "valid_json": bool(ok),
                        "reasoning_tokens": rt,
                    }
                else:
                    record(f"reasoning_effort={effort}", False, **{**meta, **_err(r, key)})
                    efforts[effort] = {"accepted": False}
            report["accepted_options"]["reasoning_effort"] = efforts

            # 4) schema-constrained output, independent of 3
            schema = {
                "type": "object",
                "properties": {"answer": {"type": "integer"}},
                "required": ["answer"],
                "additionalProperties": False,
            }
            data, meta, r = await chat(
                {
                    "messages": [{"role": "user", "content": "Give answer=7."}],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {"name": "probe", "schema": schema, "strict": True},
                    },
                    **lim,
                }
            )
            if data is not None:
                txt = data["choices"][0]["message"].get("content") or ""
                try:
                    ok = isinstance(json.loads(txt).get("answer"), int)
                except (ValueError, AttributeError):
                    ok = False
                fr = data["choices"][0].get("finish_reason")
                record(
                    "json_schema",
                    ok,
                    parsed_ok=ok,
                    finish_reason=fr,
                    status=(
                        "ok"
                        if ok
                        else (
                            "inconclusive_truncated"
                            if fr == "length"
                            else "accepted_but_output_invalid"
                        )
                    ),
                    **meta,
                )
                report["accepted_options"]["json_schema"] = bool(ok)
            else:
                record("json_schema", False, **{**meta, **_err(r, key)})
                report["accepted_options"]["json_schema"] = False

            # 5) seed + temperature
            data, meta, r = await chat(
                {
                    "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
                    "seed": 1,
                    "temperature": 0,
                    **lim,
                }
            )
            record(
                "seed_and_temperature",
                data is not None,
                **{**meta, **({} if data is not None else _err(r, key))},
            )
            report["accepted_options"]["seed"] = data is not None
        except ProbeAborted as e:
            report["aborted"] = str(e)
        except httpx.TransportError as e:
            report["aborted"] = f"network failure: {type(e).__name__}"

    report["calls_made"], report["tokens_observed"] = budget.calls, budget.tokens
    report["returned_model_ids"] = sorted(returned)
    report["usage_fields_seen"] = sorted(usage_keys)
    ok = {c["name"]: c["ok"] for c in report["checks"]}
    report["summary"] = {
        "authenticated": any(
            ok.get(n, False) for n in ("list_models", "small_cap_behaviour", "minimal_completion")
        ),
        "model_identity_matches_request": bool(returned) and returned == {model},
        "recommended_json_mode": (
            "json_schema"
            if report["accepted_options"].get("json_schema")
            else "json_object" if report["accepted_options"].get("json_object") else "prompt_only"
        ),
        "usage_reported": bool(usage_keys),
        "json_schema_status": next(
            (c.get("status") for c in report["checks"] if c["name"] == "json_schema"), None
        ),
        "assumptions_in_adapter": {"json_mode_default": True, "limit_field_default": "max_tokens"},
    }
    return json.loads(json.dumps(report, default=str).replace(key, "<redacted>")) if key else report
