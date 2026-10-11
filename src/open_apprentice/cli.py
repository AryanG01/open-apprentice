"""Open Apprentice CLI (`oa`).

Registers the full command surface from spec §24.5 now, at M0, even though most commands are
not implemented yet. An unimplemented command exits with ExitState.NOT_IMPLEMENTED and says so
plainly -- it must never pretend to succeed. This lets `oa --help` and every command's `--help`
work from the first commit, and lets scripts/tests probe "is this wired up" independently of
"does this work yet".
"""

from __future__ import annotations

import sys
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
        for e, c in trials:
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
                )
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
    dry_run: bool = DryRunOpt,
    config: Optional[str] = ConfigOpt,
    max_usd: Optional[float] = MaxUsdOpt,
    live: bool = LiveOpt,
) -> None:
    """Offline evidence replay; spends no credits."""
    _not_implemented("replay-evidence", "M5")


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


def main() -> None:
    try:
        app()
    except NotImplementedExit as e:
        typer.echo(str(e), err=True)
        sys.exit(int(ExitState.NOT_IMPLEMENTED))


if __name__ == "__main__":
    main()
