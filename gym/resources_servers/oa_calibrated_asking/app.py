"""Open Apprentice 'calibrated asking' as a NeMo Gym resources server.

An agent sees one demonstration of a hidden layout rule, may call `ask` (the teacher shows the true outcome on a new input; at most 3,
each costs), then calls `commit` with a rule in a closed text grammar, or `abstain`. `verify` scores the episode with exact rational
evaluation against held-out scenes (no LLM judge) and returns SEPARATE reward components; the named scalar `reward` is the single
component `correct`, not a sum or a blend. The environment logic lives in the Open Apprentice package (evaluation/asking_env.py);
this file is the thin NeMo Gym wrapper around it.
"""

import asyncio
import pathlib
import sys
from typing import Any, Dict, List

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field

# gym/resources_servers/oa_calibrated_asking/app.py -> repo root is three levels up from this folder; the package is imported from ../src
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "src"))

from nemo_gym.base_resources_server import (  # noqa: E402
    BaseMultiRewardVerifyResponse,
    BaseResourcesServerConfig,
    BaseSeedSessionRequest,
    BaseSeedSessionResponse,
    BaseVerifyRequest,
    ReverifyMode,
    SimpleResourcesServer,
)
from nemo_gym.server_utils import SESSION_ID_KEY  # noqa: E402

from open_apprentice.evaluation.asking_env import AskingEnv  # noqa: E402


class OACalibratedAskingConfig(BaseResourcesServerConfig):
    # The episode lives in this server's memory, so a recorded rollout cannot be re-scored without re-running it.
    REVERIFY_MODE = ReverifyMode.UNSUPPORTED


class EpisodeFields(BaseModel):
    split: str = "development"
    seed: int = 0
    index: int
    kind: str  # badge | spacing


class SeedSessionRequest(BaseSeedSessionRequest, EpisodeFields):
    pass


class AskRequest(BaseModel):
    card_widths: List[int]


class CommitRequest(BaseModel):
    rule: str


class AbstainRequest(BaseModel):
    reason: str = ""


class VerifyRequest(BaseVerifyRequest, EpisodeFields):
    pass


class VerifyResponse(BaseMultiRewardVerifyResponse):
    # Each component is also a top-level number so the aggregate-metrics endpoint profiles every axis on its own.
    correct: float = 0.0
    held_out: float = 0.0
    asking: float = 0.0
    not_confidently_wrong: float = 0.0
    economy: float = 0.0
    committed: bool = False
    abstained: bool = False
    asks_used: int = 0
    ambiguous: bool = False


class OACalibratedAskingServer(SimpleResourcesServer):
    config: OACalibratedAskingConfig
    session_id_to_env: Dict[str, Any] = Field(default_factory=dict)  # session id -> AskingEnv (plain object, not a pydantic type)

    def setup_webserver(self) -> FastAPI:
        app = super().setup_webserver()
        app.post("/ask")(self.ask)
        app.post("/commit")(self.commit)
        app.post("/abstain")(self.abstain)
        return app

    async def seed_session(self, request: Request, body: SeedSessionRequest) -> BaseSeedSessionResponse:
        # building the environment solves a small satisfiability problem the first time: keep it off the event loop
        env = await asyncio.to_thread(AskingEnv, body.split, body.seed, body.index, body.kind)
        self.session_id_to_env[request.session[SESSION_ID_KEY]] = env
        return BaseSeedSessionResponse()

    def _env(self, request: Request) -> AskingEnv | None:
        return self.session_id_to_env.get(request.session[SESSION_ID_KEY])

    async def ask(self, request: Request, body: AskRequest) -> Dict[str, Any]:
        env = self._env(request)
        return env.ask({"card_widths": body.card_widths}) if env else {"ok": False, "error": "no episode: call seed_session first"}

    async def commit(self, request: Request, body: CommitRequest) -> Dict[str, Any]:
        env = self._env(request)
        return env.commit(body.rule) if env else {"ok": False, "error": "no episode: call seed_session first"}

    async def abstain(self, request: Request, body: AbstainRequest) -> Dict[str, Any]:
        env = self._env(request)
        return env.abstain() if env else {"ok": False, "error": "no episode: call seed_session first"}

    async def verify(self, request: Request, body: VerifyRequest) -> VerifyResponse:
        env = self._env(request)
        if env is None:  # the agent never seeded a session: score as an episode in which nothing happened
            env = await asyncio.to_thread(AskingEnv, body.split, body.seed, body.index, body.kind)
        s = env.score()
        c = s["components"]
        return VerifyResponse(
            **body.model_dump(),
            reward=s["reward"],
            reward_components=dict(c),
            **c,
            committed=s["committed"],
            abstained=s["abstained"],
            asks_used=s["asks_used"],
            ambiguous=s["ambiguous"],
        )


if __name__ == "__main__":
    OACalibratedAskingServer.run_webserver()
