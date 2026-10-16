"""Open Apprentice CLI (`oa`).

Registers the full command surface from spec §24.5 now, at M0, even though most commands are
not implemented yet. An unimplemented command exits with ExitState.NOT_IMPLEMENTED and says so
plainly -- it must never pretend to succeed. This lets `oa --help` and every command's `--help`
work from the first commit, and lets scripts/tests probe "is this wired up" independently of
"does this work yet".
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Optional

import typer

from open_apprentice.cli_exit import ExitState, NotImplementedExit

app = typer.Typer(
    name="oa",
    help="Open Apprentice: teach, transfer, and repair portable visual rules.",
    no_args_is_help=True,
)

config_app = typer.Typer(help="Configuration bootstrap.", no_args_is_help=True)
app.add_typer(config_app, name="config")
admin_app = typer.Typer(help="Administration.", no_args_is_help=True)
app.add_typer(admin_app, name="admin")
db_app = typer.Typer(help="Database.", no_args_is_help=True)
app.add_typer(db_app, name="db")
provider_app = typer.Typer(help="Inference provider.", no_args_is_help=True)
app.add_typer(provider_app, name="provider")
demo_app = typer.Typer(help="Demo data.", no_args_is_help=True)
app.add_typer(demo_app, name="demo")
benchmark_app = typer.Typer(help="Frozen benchmarks.", no_args_is_help=True)
app.add_typer(benchmark_app, name="benchmark")
eval_app = typer.Typer(help="Plan 5 evaluation battery.", no_args_is_help=True)
app.add_typer(eval_app, name="eval")


def _not_implemented(command: str, milestone: str) -> None:
    """Report an unimplemented command loudly and exit with a distinct, documented code."""
    typer.echo(
        f"oa {command}: NOT_IMPLEMENTED (planned for {milestone}). "
        "This command is registered but not yet built -- it does not run a fake success.",
        err=True,
    )
    raise typer.Exit(code=int(ExitState.NOT_IMPLEMENTED))


# Common options shared by the expensive commands per §24.5: every expensive command accepts
# dry-run/offline inspection, a configuration path, and an explicit budget ceiling.
DryRunOpt = typer.Option(False, "--dry-run", help="Report the planned work without spending.")
ConfigOpt = typer.Option(None, "--config", help="Path to a configs/*.yaml protocol file.")
MaxUsdOpt = typer.Option(None, "--max-usd", help="Explicit spending ceiling for this command.")
LiveOpt = typer.Option(False, "--live", help="Use the real Nebius/Nemotron provider.")


# ---------------------------------------------------------------------------
# Commands implemented for real at M0.
# ---------------------------------------------------------------------------


@app.command()
def doctor() -> None:
    """Offline capability/config check. Spends no credits (§14.3). Never prints secret values."""
    from open_apprentice.config import load_settings, describe_settings_safely

    typer.echo("oa doctor -- offline checks only, no network calls, no credits spent.\n")
    settings = load_settings()
    for line in describe_settings_safely(settings):
        typer.echo(line)

    problems = settings.validation_problems()
    if problems:
        typer.echo("\nProblems found:")
        for p in problems:
            typer.echo(f"  - {p}")
        raise typer.Exit(code=int(ExitState.VALIDATION_FAILED))
    typer.echo(
        "\nConfiguration looks internally consistent. This does NOT verify live provider access."
    )
    typer.echo("Run `oa provider probe --live --max-usd <N>` to check the real Nebius endpoint.")


@config_app.command("init")
def config_init(
    env_file: str = typer.Option(
        ".env", "--env-file", help="Path to the .env file to create/update."
    ),
) -> None:
    """Create or update .env from .env.example, generating a session secret, without printing it."""
    from open_apprentice.bootstrap import init_env_file

    result = init_env_file(env_file)
    for line in result.messages:
        typer.echo(line)
    if not result.ok:
        raise typer.Exit(code=int(ExitState.VALIDATION_FAILED))


# ---------------------------------------------------------------------------
# Registered but not yet built. Each exits NOT_IMPLEMENTED (code 2) -- never a fake success.
# Expensive commands accept --dry-run/--config/--max-usd per spec 24.5.
# ---------------------------------------------------------------------------


@admin_app.command("create")
def admin_create(
    dry_run: bool = DryRunOpt,
    config: Optional[str] = ConfigOpt,
    max_usd: Optional[float] = MaxUsdOpt,
    live: bool = LiveOpt,
) -> None:
    """Create the owner account (interactive password)."""
    _not_implemented("admin create", "M1")


@db_app.command("upgrade")
def db_upgrade(
    dry_run: bool = DryRunOpt,
    config: Optional[str] = ConfigOpt,
    max_usd: Optional[float] = MaxUsdOpt,
    live: bool = LiveOpt,
) -> None:
    """Run Alembic migrations."""
    _not_implemented("db upgrade", "M1")


@provider_app.command("probe")
def provider_probe(
    dry_run: bool = DryRunOpt,
    config: Optional[str] = ConfigOpt,
    max_usd: Optional[float] = MaxUsdOpt,
    live: bool = LiveOpt,
    output: str = typer.Option(
        "docs/capabilities.json", "--output", help="Where to write the credential-free report."
    ),
) -> None:
    """Probe the real Nebius endpoint (spec 14.3): model list, completion-limit field, JSON modes, usage, seed.

    Offline by default (prints the plan, spends nothing). `--live` makes at most 8 tiny requests under a hard
    token ceiling and needs an explicit --max-usd not above LIVE_RUN_MAX_USD."""
    import asyncio
    import json
    import os
    import tempfile

    from open_apprentice.config import load_settings
    from open_apprentice.providers.capabilities import (
        MAX_CALLS,
        MAX_TOTAL_TOKENS,
        ProbeAborted,
        run_probe,
    )

    st = load_settings()
    typer.echo(
        f"oa provider probe  mode={st.provider_mode}  model={st.nebius_model}  base={st.nebius_base_url}"
    )
    if not live or dry_run:
        typer.echo(
            f"DRY RUN: would make <= {MAX_CALLS} requests (<= {MAX_TOTAL_TOKENS} tokens total): GET /models, minimal completion, "
            "json_object, json_schema, seed. Nothing sent. Re-run with --live --max-usd N."
        )
        return
    if st.provider_mode != "nebius" or not st._raw_env.get("NEBIUS_API_KEY"):
        typer.echo(
            "BLOCKED_NO_CREDENTIAL: set PROVIDER_MODE=nebius and NEBIUS_API_KEY in .env. Live integration NOT verified.",
            err=True,
        )
        raise typer.Exit(code=int(ExitState.BLOCKED_NO_CREDENTIAL))
    ceiling = float(st.live_run_max_usd) if st.live_run_max_usd else None
    if max_usd is None or ceiling is None or max_usd > ceiling:
        typer.echo(
            f"BUDGET: pass --max-usd N with N <= LIVE_RUN_MAX_USD ({st.live_run_max_usd or 'unset'}).",
            err=True,
        )
        raise typer.Exit(code=int(ExitState.BUDGET_EXCEEDED))
    try:
        rep = asyncio.run(run_probe(st))
    except ProbeAborted as e:
        typer.echo(f"probe aborted: {e}", err=True)
        raise typer.Exit(code=int(ExitState.BLOCKED_NO_CREDENTIAL))
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(output) or ".", prefix=".cap.")
    with os.fdopen(fd, "w") as f:
        json.dump(rep, f, indent=2, sort_keys=True)
    os.replace(tmp, output)
    for c in rep["checks"]:
        typer.echo(
            f"  [{'ok' if c['ok'] else 'FAIL':4s}] {c['name']}  "
            + ", ".join(
                f"{k}={c[k]}"
                for k in (
                    "http_status",
                    "limit_field",
                    "finish_reason",
                    "parsed_ok",
                    "returned_model",
                    "model_count",
                    "requested_model_listed",
                    "latency_ms",
                )
                if k in c
            )
        )
    s = rep["summary"]
    typer.echo(
        f"calls={rep['calls_made']} tokens_observed={rep['tokens_observed']} usage_fields={rep['usage_fields_seen']} returned_models={rep['returned_model_ids']}"
    )
    typer.echo(f"summary: {s}")
    if rep.get("aborted"):
        typer.echo(f"aborted: {rep['aborted']}", err=True)
    typer.echo(f"report written to {output} (no credentials in it)")
    if not (s["authenticated"] and s["model_identity_matches_request"]):
        raise typer.Exit(code=int(ExitState.VALIDATION_FAILED))


@demo_app.command("seed")
def demo_seed(
    dry_run: bool = DryRunOpt,
    config: Optional[str] = ConfigOpt,
    max_usd: Optional[float] = MaxUsdOpt,
    live: bool = LiveOpt,
) -> None:
    """Seed demo tasks."""
    _not_implemented("demo seed", "M1")


@app.command("run")
def run(
    dry_run: bool = DryRunOpt,
    config: Optional[str] = ConfigOpt,
    max_usd: Optional[float] = MaxUsdOpt,
    live: bool = LiveOpt,
) -> None:
    """Run a task with a policy."""
    _not_implemented("run", "M1")


@app.command("learn-oog")
def learn_oog(
    arm: str = typer.Option(
        ..., "--arm", help="model | hybrid | search (search uses NO model and costs nothing)"
    ),
    reps: int = typer.Option(1, "--reps"),
    live: bool = LiveOpt,
    max_tokens: int = typer.Option(60000, "--max-tokens", help="Hard token ceiling PER TRIAL."),
    max_calls: int = typer.Option(8, "--max-calls"),
    completion_cap: int = typer.Option(32000, "--completion-cap"),
    max_total_tokens: int = typer.Option(
        300_000,
        "--max-total-tokens",
        help="GLOBAL model-token ceiling; later trials are skipped and reported.",
    ),
    output_dir: str = typer.Option("results/exp_oog", "--output-dir"),
) -> None:
    """Out-of-grammar battery (development only): rules the symbolic search cannot express. Saves every trial as it finishes."""
    import asyncio
    import json
    import os

    from open_apprentice.config import load_settings
    from open_apprentice.evaluation.oog import RULES
    from open_apprentice.evaluation.pilot import run_oog_trial
    from open_apprentice.providers.factory import MissingCredential, make_provider

    if arm not in ("model", "hybrid", "search"):
        typer.echo("--arm must be model, hybrid or search", err=True)
        raise typer.Exit(code=1)
    st = load_settings()
    trials = [i for _ in range(reps) for i in range(len(RULES))]
    typer.echo(
        f"oa learn-oog  arm={arm} trials={len(trials)} model={'none' if arm == 'search' else st.nebius_model}"
    )
    if arm != "search" and not live:
        typer.echo(
            "DRY RUN: add --live to spend model credit (global ceiling applies). The search arm needs no flag."
        )
        return
    provider = None
    if arm != "search":
        try:
            provider = make_provider(st)
        except MissingCredential as e:
            typer.echo(f"BLOCKED_NO_CREDENTIAL: {e}", err=True)
            raise typer.Exit(code=int(ExitState.BLOCKED_NO_CREDENTIAL))

    async def main() -> None:
        spent = 0
        os.makedirs(output_dir, exist_ok=True)
        for k, i in enumerate(trials):
            if spent >= max_total_tokens:
                typer.echo(f"NOT RUN: global token ceiling {max_total_tokens} reached (rule {i})")
                continue
            r = await run_oog_trial(provider, i, max_tokens_total=max_tokens, max_calls=max_calls, reasoning_effort=st.nebius_reasoning_effort,
                                    completion_cap=completion_cap, hybrid=(arm != "model"))  # fmt: skip
            r["arm"], r["rep"] = arm, k // len(RULES)
            spent += r["tokens"]
            with open(os.path.join(output_dir, f"oog-{arm}-r{r['rep']}-rule{i}.json"), "w") as f:
                json.dump(r, f, indent=2, default=str)
            typer.echo(
                f"saved rule{i} rep{r['rep']}: {r['final_state']} recovered={r['recovered_latent_on_heldout']} tokens={r['tokens']} (total {spent})"
            )
        if provider is not None:
            await provider.aclose()

    asyncio.run(main())
    typer.echo(f"results in {output_dir}")


@app.command("learn")
def learn(
    dry_run: bool = DryRunOpt,
    config: Optional[str] = ConfigOpt,
    max_usd: Optional[float] = MaxUsdOpt,
    live: bool = LiveOpt,
    split: str = typer.Option(
        "development",
        "--split",
        help="Only 'development' or 'validation' may be used before the freeze.",
    ),
    episode: int = typer.Option(0, "--episode", help="First episode index."),
    episodes: int = typer.Option(1, "--episodes", help="How many consecutive episodes."),
    concept: str = typer.Option("badge", "--concept", help="badge | spacing | both"),
    max_tokens: int = typer.Option(40000, "--max-tokens", help="Hard token ceiling PER TRIAL."),
    max_calls: int = typer.Option(8, "--max-calls", help="Hard model-call ceiling PER TRIAL."),
    completion_cap: int = typer.Option(
        6000, "--completion-cap", help="Max completion tokens per model call (reasoning shares it)."
    ),
    audit: bool = typer.Option(
        False,
        "--audit",
        help="One extra generation round that hunts for other rules fitting all evidence (abstains on a real disagreement).",
    ),
    reps: int = typer.Option(
        1, "--reps", help="Repeat every trial this many times (fresh model samples)."
    ),
    hybrid: bool = typer.Option(
        False,
        "--hybrid",
        help="Union the model's rules with the bounded symbolic search over a declared grammar.",
    ),
    max_total_tokens: int = typer.Option(
        600_000,
        "--max-total-tokens",
        help="GLOBAL model-token ceiling for the whole command; later trials are skipped and reported.",
    ),
    output_dir: str = typer.Option("results/pilot", "--output-dir"),
) -> None:
    """Teaching-only trials with the live model on development episodes (spec 21.11 pilot question 1)."""
    import asyncio
    import json
    import os

    from open_apprentice.config import load_settings
    from open_apprentice.evaluation.pilot import run_learn_trial
    from open_apprentice.providers.factory import MissingCredential, make_provider

    if split == "final":
        typer.echo(
            "REFUSED: the final split is not run during development (it would be peeking before the freeze).",
            err=True,
        )
        raise typer.Exit(code=int(ExitState.VALIDATION_FAILED))
    concepts = ["badge", "spacing"] if concept == "both" else [concept]
    trials = [
        (e, c) for _ in range(reps) for e in range(episode, episode + episodes) for c in concepts
    ]
    st = load_settings()
    typer.echo(
        f"oa learn  split={split} trials={len(trials)}  model={st.nebius_model}  reasoning_effort={st.nebius_reasoning_effort or 'provider default'}"
    )
    if not live or dry_run:
        typer.echo(
            f"DRY RUN: would run {len(trials)} trial(s), each <= {max_calls} model calls / {max_tokens} tokens. Nothing sent. Add --live --max-usd N."
        )
        return
    ceiling = float(st.live_run_max_usd) if st.live_run_max_usd else None
    if max_usd is None or ceiling is None or max_usd > ceiling:
        typer.echo(
            f"BUDGET: pass --max-usd N with N <= LIVE_RUN_MAX_USD ({st.live_run_max_usd or 'unset'}).",
            err=True,
        )
        raise typer.Exit(code=int(ExitState.BUDGET_EXCEEDED))
    try:
        provider = make_provider(st)
    except MissingCredential as e:
        typer.echo(f"BLOCKED_NO_CREDENTIAL: {e}", err=True)
        raise typer.Exit(code=int(ExitState.BLOCKED_NO_CREDENTIAL))

    async def main() -> list[dict]:
        out = []
        spent = 0
        for e, c in trials:
            if spent >= max_total_tokens:
                typer.echo(
                    f"NOT RUN: global token ceiling {max_total_tokens} reached (episode {e}, {c})"
                )
                continue
            out.append(
                await run_learn_trial(
                    provider,
                    split,
                    e,
                    c,
                    max_tokens_total=max_tokens,
                    max_calls=max_calls,
                    reasoning_effort=st.nebius_reasoning_effort,
                    completion_cap=completion_cap,
                    audit=audit,
                    hybrid=hybrid,
                )
            )
            spent += out[-1]["tokens"]
            os.makedirs(
                output_dir, exist_ok=True
            )  # save EVERY trial the moment it finishes: a crash or a stall must not lose paid work
            r = out[-1]
            with open(
                os.path.join(
                    output_dir,
                    f"learn-{split}-ep{r['episode']}-{r['concept']}-{r['ran_at'].replace(':', '')}.json",
                ),
                "w",
            ) as f:
                json.dump(r, f, indent=2, default=str)
            typer.echo(
                f"saved ep{r['episode']} {r['concept']}: {r['final_state']} recovered={r['recovered_latent_on_heldout']} tokens={r['tokens']} (total {spent})"
            )
        await provider.aclose()
        return out

    results = asyncio.run(main())
    os.makedirs(output_dir, exist_ok=True)
    typer.echo(
        f"{'ep':>3} {'concept':8s} {'template':10s} {'state':11s} {'rounds':>6} {'queries':>7} {'teach':>9} {'recovered':>9} {'tokens':>7} {'wall_s':>6}  note"
    )
    for r in results:
        path = os.path.join(
            output_dir,
            f"learn-{split}-ep{r['episode']}-{r['concept']}-{r['ran_at'].replace(':', '')}.json",
        )
        with open(path, "w") as f:
            json.dump(r, f, indent=2, default=str)
        t = r["teacher_interactions"]
        typer.echo(
            f"{r['episode']:>3} {r['concept']:8s} {r['evaluator_template']:10s} {r['final_state']:11s} {r['rounds']:>6} {r['queries']:>7} "
            f"{t['answers']}a/{t['corrections']}c {str(r['recovered_latent_on_heldout']):>9} {r['tokens']:>7} {r['wall_s']:>6}  {r['error'] or ''}"
        )
    ok = sum(1 for r in results if r["recovered_latent_on_heldout"])
    typer.echo(
        f"recovered the hidden rule on held-out scenes: {ok}/{len(results)}  |  total tokens {sum(r['tokens'] for r in results)}  |  results in {output_dir}"
    )


@app.command("teach")
def teach(
    dry_run: bool = DryRunOpt,
    config: Optional[str] = ConfigOpt,
    max_usd: Optional[float] = MaxUsdOpt,
    live: bool = LiveOpt,
) -> None:
    """Create a durable teaching session."""
    _not_implemented("teach", "M2")


@app.command("transfer")
def transfer(
    dry_run: bool = DryRunOpt,
    config: Optional[str] = ConfigOpt,
    max_usd: Optional[float] = MaxUsdOpt,
    live: bool = LiveOpt,
) -> None:
    """Bind a concept to another backend."""
    _not_implemented("transfer", "M3")


@app.command("compose")
def compose(
    dry_run: bool = DryRunOpt,
    config: Optional[str] = ConfigOpt,
    max_usd: Optional[float] = MaxUsdOpt,
    live: bool = LiveOpt,
) -> None:
    """Run a bounded two-concept composition."""
    _not_implemented("compose", "M4")


@app.command("compare")
def compare(
    dry_run: bool = DryRunOpt,
    config: Optional[str] = ConfigOpt,
    max_usd: Optional[float] = MaxUsdOpt,
    live: bool = LiveOpt,
    split: str = typer.Option(
        "development",
        "--split",
        help="development | validation (final is refused before the freeze)",
    ),
    episode: int = typer.Option(0, "--episode", help="First episode index."),
    episodes: int = typer.Option(1, "--episodes", help="How many consecutive episodes."),
    methods: str = typer.Option(
        "enumerative_reference,full_v1_2,fresh_full_context,text_memory,structured_procedure",
        "--methods",
    ),
    output_dir: str = typer.Option("results/runs", "--output-dir"),
    max_total_tokens: int = typer.Option(
        2_000_000,
        "--max-total-tokens",
        help="GLOBAL model-token ceiling for this whole command; remaining runs are skipped and reported.",
    ),
) -> None:
    """Run methods over episodes through the shared runner (spec 21.11). Needs Chromium: run outside restrictive sandboxes."""
    import asyncio
    import json
    import os
    import time

    from open_apprentice.config import load_settings
    from open_apprentice.evaluation.local_engine import local_engine
    from open_apprentice.evaluation.pilot import policy_registry, run_compare
    from open_apprentice.evaluation.report import build_report, render_markdown
    from open_apprentice.evaluation.runner import EPISODE_LIMITS

    if split == "final":
        typer.echo("REFUSED: the final split is not run before the freeze.", err=True)
        raise typer.Exit(code=int(ExitState.VALIDATION_FAILED))
    reg = policy_registry()
    names = [m.strip() for m in methods.split(",") if m.strip()]
    bad = [m for m in names if m not in reg]
    if bad:
        typer.echo(f"unknown method(s) {bad}; choose from {sorted(reg)}", err=True)
        raise typer.Exit(code=int(ExitState.VALIDATION_FAILED))
    model_methods = [m for m in names if reg[m].uses_model]
    runs = episodes * len(names)
    ceil_tokens = episodes * len(model_methods) * EPISODE_LIMITS.tokens
    st = load_settings()
    typer.echo(
        f"oa compare  split={split} episodes={episode}..{episode + episodes - 1} methods={names}"
    )
    typer.echo(
        f"matrix: {runs} runs ({episodes} episodes x {len(names)} methods); model-based runs: {episodes * len(model_methods)}; "
        f"hard ceiling per run: {EPISODE_LIMITS.tokens} tokens / {EPISODE_LIMITS.calls} calls / {EPISODE_LIMITS.actions} actions; "
        f"worst-case model tokens: {ceil_tokens} (global ceiling {max_total_tokens}); reasoning_effort={st.nebius_reasoning_effort or 'provider default'}"
    )
    if not live or dry_run:
        typer.echo("DRY RUN: nothing started, nothing sent. Add --live --max-usd N.")
        return
    provider = None
    if model_methods:
        from open_apprentice.providers.factory import MissingCredential, make_provider

        ceiling = float(st.live_run_max_usd) if st.live_run_max_usd else None
        if max_usd is None or ceiling is None or max_usd > ceiling:
            typer.echo(
                f"BUDGET: pass --max-usd N with N <= LIVE_RUN_MAX_USD ({st.live_run_max_usd or 'unset'}).",
                err=True,
            )
            raise typer.Exit(code=int(ExitState.BUDGET_EXCEEDED))
        try:
            provider = make_provider(st)
        except MissingCredential as e:
            typer.echo(f"BLOCKED_NO_CREDENTIAL: {e}", err=True)
            raise typer.Exit(code=int(ExitState.BLOCKED_NO_CREDENTIAL))
    stamp = time.strftime("%Y%m%dT%H%M%S")
    out = os.path.join(output_dir, f"{split}-ep{episode}-{episodes}-{stamp}")
    os.makedirs(out, exist_ok=True)

    async def main() -> dict:
        with local_engine(".") as (url, token):
            res = await run_compare(
                split,
                episode,
                episodes,
                names,
                provider,
                url,
                token,
                rows_path=os.path.join(out, "rows.jsonl"),
                global_token_ceiling=max_total_tokens,
            )
        if provider is not None:
            await provider.aclose()
        return res

    res = asyncio.run(main())
    rows, errors = res["rows"], res["errors"]
    if errors:
        typer.echo(
            f"INFRA ERRORS ({len(errors)} runs missing from the results): {json.dumps(errors)[:600]}",
            err=True,
        )
    if rows:
        prim = (
            ("full_v1_2", "structured_procedure")
            if {"full_v1_2", "structured_procedure"} <= set(names)
            else (names[0], names[0])
        )
        rep = build_report(rows, names, prim, f"{split}-pilot", allow_mock=True)
        rep["split_note"] = (
            f"{split.upper()} data, episodes {episode}..{episode + episodes - 1}; development tuning/diagnostics, NOT the locked study"
        )
        rep["infra_errors"] = errors
        with open(os.path.join(out, "report.json"), "w") as f:
            json.dump(rep, f, indent=2, default=str)
        with open(os.path.join(out, "report.md"), "w") as f:
            f.write(render_markdown(rep))
        typer.echo(
            f"{'method':24s} {'correct/sched':>14s} {'cond.':>8s} {'false_succ':>11s} {'tokens':>8s} {'calls':>6s} {'actions':>8s} {'teacher':>8s}  failures"
        )
        for m in names:
            s = rep["methods_all_stages"][m]
            su, co, fs, c = s["success"], s["conditional"], s["false_success"], s["costs"]
            typer.echo(
                f"{m:24s} {su['correct']:>6d}/{su['scheduled']:<7d} {str(co['rate'])[:6]:>8s} {fs['false_successes']:>5d}/{fs['claimed_successes']:<5d} "
                f"{c['tokens']:>8d} {c['calls']:>6d} {c['actions']:>8d} {c['teacher_interactions']:>8d}  {json.dumps(s['failures'])}"
            )
    typer.echo(f"results in {out}")


@benchmark_app.command("freeze")
def benchmark_freeze(
    dry_run: bool = DryRunOpt,
    config: Optional[str] = ConfigOpt,
    max_usd: Optional[float] = MaxUsdOpt,
    live: bool = LiveOpt,
) -> None:
    """Freeze an evaluation manifest."""
    _not_implemented("benchmark freeze", "M6")


@benchmark_app.command("run")
def benchmark_run(
    dry_run: bool = DryRunOpt,
    config: Optional[str] = ConfigOpt,
    max_usd: Optional[float] = MaxUsdOpt,
    live: bool = LiveOpt,
) -> None:
    """Run a frozen benchmark."""
    _not_implemented("benchmark run", "M6")


@app.command("report")
def report(
    run_dir: str = typer.Option(
        ..., "--run-dir", help="a results/runs/<id> directory containing rows.jsonl"
    ),
    primary: str = typer.Option("full_v1_2", "--primary"),
    versus: str = typer.Option("structured_procedure", "--versus"),
    write: bool = typer.Option(
        False, "--write", help="write report.json and report.md into the run directory"
    ),
) -> None:
    """Rebuild a report from the STORED rows of one run (nothing is re-run, nothing is typed by hand)."""
    import dataclasses
    import json
    import os

    from open_apprentice.evaluation.metrics import Row
    from open_apprentice.evaluation.report import EmptyResults, build_report, render_markdown

    path = os.path.join(run_dir, "rows.jsonl")
    if not os.path.exists(path):
        typer.echo(f"oa report: no rows.jsonl in {run_dir}", err=True)
        raise typer.Exit(code=1)
    fields = {f.name for f in dataclasses.fields(Row)}
    rows = [
        Row(**{k: v for k, v in json.loads(line).items() if k in fields})
        for line in open(path)
        if line.strip()
    ]
    methods = sorted({r.method for r in rows})
    try:
        rep = build_report(
            rows, methods, (primary, versus), config_id=os.path.basename(os.path.normpath(run_dir))
        )
    except EmptyResults as e:
        typer.echo(f"oa report: {e}", err=True)
        raise typer.Exit(code=1)
    rep["source_run"] = os.path.basename(os.path.normpath(run_dir))
    if not rep["source_run"].startswith("final"):
        rep["gates_27_5"] = {
            "status": "not_evaluated_on_non_final_runs",
            "caveat": "spec 27.5 gates apply to the locked final study only; this is a development/pilot run",
        }
        rep["label"] += " | DEVELOPMENT/PILOT RUN, NOT THE LOCKED STUDY"
    md = render_markdown(rep)
    typer.echo(md)
    if write:
        with open(os.path.join(run_dir, "report.json"), "w") as f:
            json.dump(rep, f, indent=2, default=str)
        with open(os.path.join(run_dir, "report.md"), "w") as f:
            f.write(md)


@app.command("replay")
def replay(
    dry_run: bool = DryRunOpt,
    config: Optional[str] = ConfigOpt,
    max_usd: Optional[float] = MaxUsdOpt,
    live: bool = LiveOpt,
) -> None:
    """Replay a saved run."""
    _not_implemented("replay", "M3")


@app.command("export-skill")
def export_skill(
    dry_run: bool = DryRunOpt,
    config: Optional[str] = ConfigOpt,
    max_usd: Optional[float] = MaxUsdOpt,
    live: bool = LiveOpt,
) -> None:
    """Export a sanitized skill package."""
    _not_implemented("export-skill", "M3")


@app.command("challenge")
def challenge(
    dry_run: bool = DryRunOpt,
    config: Optional[str] = ConfigOpt,
    max_usd: Optional[float] = MaxUsdOpt,
    live: bool = LiveOpt,
) -> None:
    """Challenge a concept with fresh inputs."""
    _not_implemented("challenge", "M2")


@app.command("export-svg")
def export_svg(
    dry_run: bool = DryRunOpt,
    config: Optional[str] = ConfigOpt,
    max_usd: Optional[float] = MaxUsdOpt,
    live: bool = LiveOpt,
) -> None:
    """Export editable SVG."""
    _not_implemented("export-svg", "M5")


@app.command("replay-evidence")
def replay_evidence(
    package: str = typer.Argument(
        ..., help="an evidence package downloaded from the live demo (evidence.json)"
    ),
) -> None:
    """Re-check an evidence package OFFLINE: hash chain, sealed concept hash, native-program hash, exact geometry, and the package's own claims.
    Needs no engine, no model and no network; spends nothing."""
    import json
    import os

    from open_apprentice.evaluation.replay import replay_package

    if not os.path.exists(package):
        typer.echo(f"oa replay-evidence: no such file: {package}", err=True)
        raise typer.Exit(code=1)
    try:
        pkg = json.load(open(package))
    except ValueError:
        typer.echo("oa replay-evidence: not valid JSON", err=True)
        raise typer.Exit(code=1)
    res = replay_package(pkg)
    for c in res["checks"]:
        tag = "INFO" if c["passed"] is None else ("PASS" if c["passed"] else "FAIL")
        typer.echo(f"{tag}  {c['name']}  ({c['detail']})")
    typer.echo(
        "RESULT: every offline check passed"
        if res["passed"]
        else "RESULT: at least one offline check FAILED"
    )
    typer.echo(
        "Scope: this re-derives hashes and geometry from the package; it does not re-run the graphics engine."
    )
    raise typer.Exit(code=0 if res["passed"] else int(ExitState.VALIDATION_FAILED))


@app.command("import-svg")
def import_svg(
    dry_run: bool = DryRunOpt,
    config: Optional[str] = ConfigOpt,
    max_usd: Optional[float] = MaxUsdOpt,
    live: bool = LiveOpt,
) -> None:
    """v1.3: import a provenance-checked SVG asset."""
    _not_implemented("import-svg", "M5")


@app.command("svg-apply")
def svg_apply(
    dry_run: bool = DryRunOpt,
    config: Optional[str] = ConfigOpt,
    max_usd: Optional[float] = MaxUsdOpt,
    live: bool = LiveOpt,
) -> None:
    """v1.3: apply a typed set_attribute patch to an SVG."""
    _not_implemented("svg-apply", "M5")


@app.command("svg-trial")
def svg_trial(
    dry_run: bool = DryRunOpt,
    config: Optional[str] = ConfigOpt,
    max_usd: Optional[float] = MaxUsdOpt,
    live: bool = LiveOpt,
) -> None:
    """v1.3: run the real-SVG matched pilot."""
    _not_implemented("svg-trial", "M5")


@app.command("drawio-check")
def drawio_check(file: Path, page: int = 0) -> None:
    """Parse, classify, render and measure one page of a .drawio file; print what is movable and why anything is not."""
    from open_apprentice.config import load_settings
    from open_apprentice.drawio.classify import classify
    from open_apprentice.drawio.parse import DrawioRefused, load_drawio
    from open_apprentice.drawio.render import render_page

    try:
        f = load_drawio(file.read_bytes())
        c = classify(f.pages[page])
        r = render_page(f.pages[page], load_settings().engine_url, png=False)
    except DrawioRefused as e:
        typer.echo(json.dumps({"refused": str(e)}))
        raise typer.Exit(2)
    demoted = {
        cid: "renders on more than one line"
        for cid in c.movable
        if cid in r.labels and r.labels[cid][1] > 1
    }
    typer.echo(
        json.dumps(
            {
                "doc_hash": f.doc_hash,
                "page": f.pages[page].id,
                "movable": list(c.movable),
                "fixed": list(c.fixed),
                "reasons": c.reasons,
                "demoted": demoted,
                "missing": list(r.missing),
                "profile": r.profile,
            }
        )
    )


@eval_app.command("freeze")
def eval_freeze(
    split: str = typer.Option(..., "--split", help="dev | final"),
    out: Optional[Path] = typer.Option(None, "--out", help="default: the split's battery folder"),
) -> None:
    """Author and freeze a battery split; print the content hashes to commit."""
    from open_apprentice.evaluation.battery_v2 import REPO, freeze

    if split not in ("dev", "final"):
        raise typer.BadParameter("split is dev or final")
    default = "benchmarks/final/battery" if split == "final" else "benchmarks/development/battery"
    target = out or REPO / default
    typer.echo(json.dumps({"split": split, "out": str(target), "hashes": freeze(split, target)}))


@eval_app.command("run")
def eval_run(
    split: str = typer.Option(..., "--split", help="dev | final"),
    systems: str = typer.Option("A,B,C,D", "--systems"),
    repeats: int = typer.Option(1, "--repeats"),
    mode: str = typer.Option("mock", "--mode", help="mock | live"),
    episodes: Optional[str] = typer.Option(None, "--episodes", help="comma-separated episode ids"),
    out: Optional[Path] = typer.Option(None, "--out", help="default: results/eval_v2"),
    seed: int = typer.Option(0, "--seed"),
    manifest: Optional[str] = typer.Option(
        None, "--manifest", help="live: an approved manifest id"
    ),
    cap_usd: float = typer.Option(
        0.0, "--cap-usd", help="live: run cap, at most the manifest ceiling"
    ),
) -> None:
    """Run a frozen battery split (verified against its hashes first) and write rows.jsonl + manifest.json. Live runs
    pass the paid-run gate first (approved manifest, cap within its ceiling, protected reserve untouched).
    """
    from open_apprentice.evaluation.battery_v2 import REPO
    from open_apprentice.evaluation.run_v2 import run_battery

    if split not in ("dev", "final") or mode not in ("mock", "live"):
        raise typer.BadParameter("split is dev or final; mode is mock or live")
    if mode == "live":
        from open_apprentice.evaluation.manifests_v2 import GateRefused, run_live

        def factory() -> object:  # built only after the gate passed
            from open_apprentice.config import load_settings
            from open_apprentice.providers.factory import make_provider

            return make_provider(load_settings())

        try:
            run_live(manifest, cap_usd, factory)
        except GateRefused as e:
            typer.echo(f"oa eval run --mode live: refused before any provider call: {e}", err=True)
            raise typer.Exit(2)
        except NotImplementedError as e:
            typer.echo(f"oa eval run --mode live: {e}", err=True)
            raise typer.Exit(int(ExitState.NOT_IMPLEMENTED))
    names = [s.strip() for s in systems.split(",") if s.strip()]
    if not names or set(names) - {"A", "B", "C", "D"}:
        raise typer.BadParameter("systems are a comma-separated subset of A,B,C,D")
    run_dir = run_battery(
        split,
        names,
        repeats,
        mode,
        out_root=out or REPO / "results/eval_v2",
        episodes=[e for e in (episodes or "").split(",") if e] or None,
        seed=seed,
    )
    typer.echo(json.dumps({"run_dir": str(run_dir)}))


@eval_app.command("manifest")
def eval_manifest(
    dry_run_dir: Path = typer.Option(
        Path("results/eval_v2/dryrun-20261016"), "--dry-run-dir", help="holds token_estimate.json"
    ),
) -> None:
    """Write the priced calibration manifest and the (unapproved) funded-tier manifest to docs/evaluation/manifests/."""
    from open_apprentice.evaluation.battery_v2 import REPO
    from open_apprentice.evaluation.manifests_v2 import (
        BUDGET_ROOT,
        calibration_manifest,
        funded_manifest,
    )
    from open_apprentice.evaluation.run_v2 import BATTERY_DIRS, load_split
    from open_apprentice.evaluation.spend import load_budget, spendable, spent_so_far

    tokens = json.loads((dry_run_dir / "token_estimate.json").read_text())
    final = json.loads(
        (REPO / "docs/evaluation/battery_final.md").read_text().split("```json")[1].split("```")[0]
    )
    cal = calibration_manifest(
        load_split(BATTERY_DIRS["dev"]),
        tokens,
        round(spent_so_far(BUDGET_ROOT), 4),
        spendable(load_budget(BUDGET_ROOT)),
    )
    fund = funded_manifest(
        len(final["episodes"]), 8, tokens
    )  # spec 7 T3: D on 8 clarification-required episodes
    out = REPO / "docs/evaluation/manifests"
    out.mkdir(parents=True, exist_ok=True)
    for m in (cal, fund):
        (out / f"{m['kind']}-{m['manifest_id']}.json").write_text(
            json.dumps(m, indent=1, sort_keys=True) + "\n"
        )
    typer.echo(json.dumps({"calibration": cal["manifest_id"], "funded": fund["manifest_id"]}))


@eval_app.command("report")
def eval_report(run_dir: Path = typer.Option(..., "--run-dir")) -> None:
    """Write <run-dir>/report.md: release-blocking checks first, both primary endpoints, per-stratum tables."""
    from open_apprentice.evaluation.analysis_v2 import report

    md = report(run_dir)
    (run_dir / "report.md").write_text(md)
    typer.echo(md)


@app.command("staging-check")
def staging_check(
    file: Optional[Path] = None,
    only: str = typer.Option("all", help="all | race | survival | render | tasks"),
    phase: str = typer.Option(
        "write", help="survival phase: write (before a restart) or read (after)"
    ),
) -> None:
    """Staging integration (spec 10): a conditional-update race, restart survival, and render/measure of one file. Runs
    against whatever OA_STORE points at; it creates no cloud resources."""
    from open_apprentice.storage.store import PreconditionFailed

    from open_apprentice.storage.factory import store_from_env

    store = store_from_env()
    failed = False
    if only in ("all", "race"):
        key = f"staging/race-{uuid.uuid4().hex}"
        g = store.put(key, b"0", if_generation=None)
        results = []
        for v in (b"a", b"b"):
            try:
                store.put(key, v, if_generation=g)
                results.append("ok")
            except PreconditionFailed:
                results.append("precondition")
        ok = results.count("ok") == 1 and results.count("precondition") == 1
        typer.echo(
            json.dumps(
                {
                    "check": "race",
                    "ok": ok,
                    "winners": results.count("ok"),
                    "precondition_failures": results.count("precondition"),
                }
            )
        )
        failed = failed or not ok
    if only in ("all", "survival"):
        if phase == "write":
            if store.get("staging/marker") is None:
                store.create("staging/marker", b"alive")
            typer.echo(json.dumps({"check": "survival", "phase": "write", "ok": True}))
        else:
            b = store.get("staging/marker")
            ok = b is not None and b.data == b"alive"
            typer.echo(json.dumps({"check": "survival", "phase": "read", "ok": ok}))
            failed = failed or not ok
    if only in ("all", "tasks"):
        # spec 10: one dispatch through the configured dispatcher (Cloud Tasks when OA_DISPATCH=cloudtasks)
        import time

        from open_apprentice.api.v2.context import make_v2
        from open_apprentice.api.v2.tasks import Job

        v = make_v2(os.environ.get("ENGINE_URL"))
        ping_id = uuid.uuid4().hex
        start = time.monotonic()
        v.dispatcher.submit(Job("ping", f"staging:{ping_id}", {"id": ping_id}))
        ok = False
        while time.monotonic() - start < 60:
            if v.store.get(f"staging/ping-{ping_id}") is not None:
                ok = True
                break
            time.sleep(0.25)
        v.dispatcher.close()
        typer.echo(
            json.dumps({"check": "tasks", "ok": ok, "seconds": round(time.monotonic() - start, 2)})
        )
        failed = failed or not ok
    if only in ("all", "render") and file is not None:
        drawio_check(file)
    if failed:
        raise typer.Exit(1)


def main() -> None:
    try:
        app()
    except NotImplementedExit as e:
        typer.echo(str(e), err=True)
        sys.exit(int(ExitState.NOT_IMPLEMENTED))


if __name__ == "__main__":
    main()
