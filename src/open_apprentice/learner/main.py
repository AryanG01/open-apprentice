"""The isolated learner process (spec 7 separation). The audit hook goes in before anything else of ours is imported;
the process then works in a fresh temporary directory, reads only the learner-visible episode, talks to the teacher
over JSON lines, and writes its outcome. It never sees the hidden behaviour, the scoring documents or any mark.

    python -m open_apprentice.learner.main --episode learner.json --system A|B|C|D --teacher-fds R,W
        --mode mock --seed N --out outcome.json

The evaluator starts the teacher and hands over only the two pipe ends (R: answers, W: requests), so the learner never
learns where the private episode lives. Files under benchmarks/, *.private.json and child processes are refused by
the audit hook, and every refusal (even one the code swallows) makes the outcome a boundary violation.
"""

from open_apprentice.teaching import isolation

isolation.install_learner_guard()
isolation.install_file_guard()

import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402
from fractions import Fraction  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, Callable, Optional  # noqa: E402

from open_apprentice.storage.store import LocalStore, Store  # noqa: E402
from open_apprentice.teaching import codec  # noqa: E402
from open_apprentice.teaching.accounting import Ledger  # noqa: E402
from open_apprentice.teaching.constraints import scene_from_payload  # noqa: E402
from open_apprentice.teaching.events import SessionLog  # noqa: E402
from open_apprentice.learner import synthetic_render  # noqa: E402
from open_apprentice.teaching.teacher import (  # noqa: E402
    ProtocolError,
    Request,
    Response,
    request_to_json,
    response_from_json,
)

GUARD_MESSAGE = "learner process may not import"
SUPPORTED_FIELDS = {"id", "kind", "role", "attached", "x", "y", "w", "h"}
SKILL = "skill"
FORBIDDEN_MARKERS = ("benchmarks/final", ".private.json")


class Refused(Exception):
    def __init__(self, msg: str, boundary: bool = False) -> None:
        super().__init__(msg)
        self.boundary = boundary


class ShowingTeacher:
    """The teacher over two inherited pipe ends (JSON lines), plus the scene of any generated probe it is asked about
    (the teacher process has never seen probes; a person would see the rendered document)."""

    def __init__(self, read_fd: int, write_fd: int) -> None:
        self.rf, self.wf = os.fdopen(read_fd, "r"), os.fdopen(write_fd, "w")
        self.logs: list[SessionLog] = []

    def close(self) -> None:
        self.wf.close()
        self.rf.close()

    def _probe_scene(self, scene_id: str) -> Optional[dict]:
        for log in self.logs:
            for e in log.events():
                p = e.payload
                if e.type == "SceneRegistered" and p.get("scene_id") == scene_id:
                    return p["scene"] if p.get("role") == "probe" else None
        return None

    def ask(self, req: Request) -> Response:
        d = request_to_json(req)
        scene = self._probe_scene(d["scene_id"]) if "scene_id" in d else None
        if scene is not None:
            d["scene"] = scene
        self.wf.write(json.dumps(d) + "\n")
        self.wf.flush()
        line = self.rf.readline()
        if not line:
            raise ProtocolError("teacher process closed")
        out = json.loads(line)
        if "protocol_error" in out:
            raise ProtocolError(out["protocol_error"])
        return response_from_json(out)


@dataclass
class Context:
    store: Store
    episode: dict
    teacher: ShowingTeacher
    ledger: Ledger
    mode: str
    seed: int
    worst: Fraction = Fraction(0)
    logs: dict[str, SessionLog] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)


def _unsupported(episode: dict) -> Optional[str]:
    for sid, s in sorted(episode["scenes"].items()):
        for o in s["objects"]:
            extra = sorted(set(o) - SUPPORTED_FIELDS)
            if extra:
                return f"unsupported structure: {o['id']} in {sid} has {', '.join(extra)}"
    return None


def open_learning_log(ctx: Context) -> SessionLog:
    ep = ctx.episode
    log = SessionLog(ctx.store, "learn")
    log.create(owner="learner")
    demo_ids = {d["scene_id"] for d in ep["demonstrations"]}
    for sid in [*sorted(demo_ids), *ep["batch"]]:
        scene = scene_from_payload(ep["scenes"][sid])
        log.append(
            "SceneRegistered",
            "system",
            {
                "scene_id": sid,
                "scene_hash": codec.digest(scene),
                "scene": codec.loads(codec.dumps(scene)),
                "role": "demo" if sid in demo_ids else "batch",
            },
        )
    for d in ep["demonstrations"]:
        out = {o["id"]: [o["x"], o["y"]] for o in d["after"]["objects"] if o["kind"] == "label"}
        log.append("DemonstrationRecorded", "human", {"scene_id": d["scene_id"], "output": out})
    ctx.logs["learn"] = log
    ctx.teacher.logs.append(log)
    return log


def _activate(ctx: Context, log: SessionLog) -> Optional[int]:
    from open_apprentice.skills.versions import SkillStore

    evs = log.events()
    version = next((e.payload["version"] for e in evs if e.type == "VersionStored"), None)
    if version is None:
        return None
    SkillStore(ctx.store).activate(SKILL, version, None, "learn", "learn")
    ctx.result["program"] = SkillStore(ctx.store).version(SKILL, version)["program"]
    return version


def run_correction(ctx: Context, scope_proposer: Any) -> None:
    """The teacher's corrective edit on the output the learner's active version produced (spec 5)."""
    from open_apprentice.skills.versions import SkillStore
    from open_apprentice.teaching.correction_executor import CorrectionExecutor, start_correction
    from open_apprentice.teaching.step import run_output

    c = ctx.episode["correction"]
    scenes = {k: scene_from_payload(v) for k, v in ctx.episode["scenes"].items()}
    scene = scenes[c["scene_id"]]
    version, _, _ = SkillStore(ctx.store).active(SKILL)
    rule = SkillStore(ctx.store).version(SKILL, version)["program"]["rule"]
    produced = run_output(rule, scene) or {}
    edit = {k: (codec.frac(v[0]), codec.frac(v[1])) for k, v in c["corrected_output"].items()}
    corrected = {**produced, **{k: edit[k] for k in c["mask"]}}
    extra = {k: v for k, v in scenes.items() if k != c["scene_id"]}
    log = start_correction(
        ctx.store, "correct", SKILL, c["scene_id"], scene, corrected, list(c["mask"]), extra
    )
    ctx.logs["correct"] = log
    ctx.teacher.logs.append(log)
    status = CorrectionExecutor(
        ctx.store, log, scope_proposer, ctx.teacher, ctx.ledger, worst_usd=ctx.worst
    ).run()
    out: dict[str, Any] = {"status": status, "program": None}
    if status == "activated":
        v, _, _ = SkillStore(ctx.store).active(SKILL)
        out["program"] = SkillStore(ctx.store).version(SKILL, v)["program"]
    ctx.result["correction"] = out


def _offline_proposer() -> Any:
    from open_apprentice.concepts.label_enumerative import LabelEnumerator

    return LabelEnumerator()


def system_a(ctx: Context, proposer: Any = None, config: Any = None) -> None:
    from open_apprentice.teaching.executor import Executor
    from open_apprentice.teaching.step import StepConfig

    proposer = proposer or _offline_proposer()
    log = open_learning_log(ctx)
    status = Executor(
        ctx.store,
        log,
        proposer,
        ctx.teacher,
        ctx.ledger,
        config or StepConfig(probes=True),
        worst_usd=ctx.worst,
        skill_id=SKILL,
        probe_renderer=synthetic_render,
    ).run()
    ctx.result["status"] = status
    if status == "committed":
        _activate(ctx, log)
        if ctx.episode.get("correction"):
            run_correction(ctx, proposer)


def system_c(ctx: Context) -> None:
    from open_apprentice.concepts.catalogue_programs import CatalogueProposer

    system_a(ctx, proposer=CatalogueProposer())


def system_d(ctx: Context) -> None:
    from open_apprentice.teaching.step import StepConfig

    ctx.result["question_selection"] = "uniform"
    system_a(ctx, config=StepConfig(probes=True, question_selection="uniform", seed=ctx.seed))


def system_b(ctx: Context) -> None:
    from open_apprentice.learner.agent_b import AgentBudgets, run_agent_b, scripted_policy
    from open_apprentice.providers.mock import MockProvider

    mock = MockProvider({}, functions={"agent_b": scripted_policy})
    ctx.result["policy"] = "scripted_fixture"
    ctx.result["correction_policy"] = (
        "A"  # B's corrections run the shared executor (ledger ruling, review I4)
    )
    log = open_learning_log(ctx)
    status = run_agent_b(lambda: mock, log, ctx.teacher, ctx.ledger, AgentBudgets(), ctx.worst)
    ctx.result["status"] = status
    if status == "committed":
        _activate(ctx, log)
        if ctx.episode.get("correction"):
            run_correction(ctx, _offline_proposer())


SYSTEMS: dict[str, Callable[[Context], None]] = {
    "A": system_a,
    "B": system_b,
    "C": system_c,
    "D": system_d,
}


def _terminal_reason(ctx: Context) -> Optional[str]:
    for log in ctx.logs.values():
        for e in log.events():
            if e.type in ("Abstained", "Errored"):
                return str(e.payload.get("reason", ""))
    return None


def _usage(ctx: Context) -> dict:
    total: dict[str, int] = {}
    for log in ctx.logs.values():
        for e in log.events():
            if e.type in ("ModelProposalReturned", "AgentTurn"):
                for k, v in (e.payload.get("usage") or {}).items():
                    if isinstance(v, int) and not isinstance(v, bool):
                        total[k] = total.get(k, 0) + v
    return total


def _check_inputs(episode_path: Path) -> None:
    parts = episode_path.resolve().as_posix()
    if "/benchmarks/final/" in parts:
        raise Refused("the episode file is under benchmarks/final", boundary=True)
    for k, v in os.environ.items():
        if any(m in v for m in FORBIDDEN_MARKERS):
            raise Refused(f"the environment names private evaluator files ({k})", boundary=True)


def _check_cwd() -> None:
    here = Path.cwd()
    for p in (here, *here.parents):
        if (p / "benchmarks").exists():
            raise Refused(
                f"a benchmarks/ folder is reachable from the working directory ({p})", True
            )


def _absolute_paths() -> None:
    """Relative import paths would break after the chdir (here and in the teacher process)."""
    sys.path[:] = [os.path.abspath(p) if p else p for p in sys.path]
    if os.environ.get("PYTHONPATH"):
        os.environ["PYTHONPATH"] = os.pathsep.join(
            os.path.abspath(p) for p in os.environ["PYTHONPATH"].split(os.pathsep) if p
        )


def run(args: argparse.Namespace) -> dict:
    result: dict[str, Any] = {
        "system": args.system,
        "status": "error",
        "reason": None,
        "program": None,
        "correction": None,
        "evidence_summary": {},
        "events": [],
        "usage": {},
        "spend": {},
        "probe_render": "synthetic",
        "boundary_violation": False,
        "mode": args.mode,
        "seed": args.seed,
    }
    ctx: Optional[Context] = None
    teacher: Optional[ShowingTeacher] = None
    try:
        episode_path = Path(args.episode).resolve()
        _check_inputs(episode_path)
        episode = json.loads(episode_path.read_text())
        _absolute_paths()
        os.chdir(tempfile.mkdtemp(prefix="oa-learner-"))
        _check_cwd()
        if args.mode != "mock":
            raise Refused("live learner runs are started only by the gated evaluator command")
        if args.system not in SYSTEMS:
            raise Refused(f"system {args.system} is not available")
        store = LocalStore(Path("store"))
        rfd, wfd = (int(x) for x in args.teacher_fds.split(","))
        teacher = ShowingTeacher(rfd, wfd)
        ctx = Context(store, episode, teacher, Ledger(store, Fraction(0)), args.mode, args.seed)
        ctx.result = result
        reason = _unsupported(episode)
        if reason:
            log = open_learning_log(ctx)
            log.append("Abstained", "system", {"action_id": "inputs", "reason": reason})
            result["status"] = "abstained"
        else:
            SYSTEMS[args.system](ctx)
        result["reason"] = _terminal_reason(ctx)
    except Refused as e:
        result["reason"] = str(e)
        result["refused"] = True
        result["boundary_refusal"] = e.boundary
    except ImportError as e:
        result["reason"] = f"{type(e).__name__}: {e}"
        result["boundary_violation"] = GUARD_MESSAGE in str(e)
        result["status"] = "error"
    except Exception as e:  # a crash is an outcome (error), recorded with its reason
        result["status"] = "error"
        result["reason"] = f"{type(e).__name__}: {e}"[:500]
    finally:
        if teacher is not None:
            try:
                teacher.close()
            except Exception:
                pass
    if ctx is not None:
        result["events"] = [
            {"log": name, "type": e.type, "payload": e.payload}
            for name, log in ctx.logs.items()
            for e in log.events()
        ]
        result["usage"] = _usage(ctx)
        result["spend"] = codec.loads(codec.dumps(ctx.ledger.exposure()))
    result["evaluator_modules"] = sorted(
        m for m in sys.modules if m.startswith("open_apprentice.evaluation")
    )
    result["violations"] = list(isolation.violations)
    if isolation.violations or result["evaluator_modules"]:
        result["boundary_violation"] = True
        result["status"] = "error"
    return result


def cli(argv: Optional[list[str]] = None) -> None:
    p = argparse.ArgumentParser(prog="open_apprentice.learner.main")
    p.add_argument("--episode", required=True)
    p.add_argument("--system", required=True, choices=["A", "B", "C", "D"])
    p.add_argument("--teacher-fds", required=True, help="R,W: inherited pipe ends to the teacher")
    p.add_argument("--mode", default="mock", choices=["mock", "live"])
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    out = Path(args.out).resolve()
    result = run(args)
    out.write_text(json.dumps(result, default=str))
    if result.get("refused") or result["boundary_violation"]:
        sys.exit(2)


if __name__ == "__main__":
    cli()
