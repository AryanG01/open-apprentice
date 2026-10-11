"""Concept package, evidence axes, and the append-only teaching ledger (spec 7.4, 7.5).

Four evidence axes are SEPARATE enums on purpose. There is deliberately no aggregate 'confidence' or
'verified' field anywhere in this module, and tests assert none is ever serialised (spec 7.5, 17.7).
"""

from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional


class IntentState(str, enum.Enum):
    UNRESOLVED = "unresolved"
    CONSISTENT_WITH_EXAMPLES = "consistent_with_examples"
    RESOLVED_WITHIN_CANDIDATE_SET = "resolved_within_candidate_set"
    USER_CORRECTED = "user_corrected"


class SymbolicStatus(str, enum.Enum):
    WITNESS_FOUND = "witness_found"
    NO_WITNESS_IN_MODEL = "no_witness_in_model"
    INCOMPLETE = "incomplete"
    TIMEOUT = "timeout"
    UNSUPPORTED = "unsupported"


class NativeStatus(str, enum.Enum):
    REPRODUCED_MISMATCH = "reproduced_mismatch"
    CHECKED_ON_LISTED_CASES = "checked_on_listed_cases"
    UNTESTED = "untested"
    FAILED = "failed"


class HeldOutStatus(str, enum.Enum):
    HIDDEN_DURING_EXECUTION = "hidden_during_execution"
    SCORED_AFTER_COMMITMENT = "scored_after_commitment"


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


class LedgerError(Exception):
    pass


@dataclass(frozen=True)
class LedgerEntry:
    seq: int
    kind: str  # demonstration | query | answer | corrected_example | superseded
    payload: dict
    source: str  # user | benchmark_teacher | system   (benchmark_teacher is NOT a user study)
    prev_hash: str
    hash: str


@dataclass
class TeachingLedger:
    """Append-only, hash-chained. Entries are never edited or removed: a rule change makes a NEW
    concept version and records an explicit 'superseded' entry. Native repair cannot append here."""

    entries: list[LedgerEntry] = field(default_factory=list)

    def append(self, kind: str, payload: dict, source: str) -> LedgerEntry:
        if kind not in ("demonstration", "query", "answer", "corrected_example", "superseded"):
            raise LedgerError(f"unknown ledger kind {kind!r}")
        prev = self.entries[-1].hash if self.entries else "genesis"
        body = {
            "seq": len(self.entries),
            "kind": kind,
            "payload": payload,
            "source": source,
            "prev": prev,
        }
        e = LedgerEntry(len(self.entries), kind, payload, source, prev, sha(body))
        self.entries.append(e)
        return e

    @property
    def head(self) -> str:
        return self.entries[-1].hash if self.entries else "genesis"

    def verify_chain(self) -> bool:
        prev = "genesis"
        for i, e in enumerate(self.entries):
            body = {
                "seq": i,
                "kind": e.kind,
                "payload": e.payload,
                "source": e.source,
                "prev": prev,
            }
            if e.prev_hash != prev or e.hash != sha(body):
                return False
            prev = e.hash
        return True

    def of_kind(self, *kinds: str) -> list[LedgerEntry]:
        return [e for e in self.entries if e.kind in kinds]


@dataclass(frozen=True)
class Concept:
    """Immutable portable rule. Bindings reference it; they never edit it."""

    concept_id: str
    version: int
    summary: str
    rule_json: str  # canonical JSON string => immutable copy of the rule
    input_schema: str
    preservation_constraints: tuple[str, ...]
    domain_hash: str
    ledger_hash: str
    intent_state: IntentState
    parent_version: Optional[int] = None

    @staticmethod
    def create(
        concept_id: str,
        version: int,
        summary: str,
        rule: list,
        domain_hash: str,
        ledger: TeachingLedger,
        intent_state: IntentState,
        preservation: tuple[str, ...] = ("preserve_unrelated_objects",),
        input_schema: str = "objects[2..8]+canvas/v1",
        parent_version: Optional[int] = None,
    ) -> "Concept":
        return Concept(
            concept_id,
            version,
            summary,
            canonical(rule),
            input_schema,
            tuple(preservation),
            domain_hash,
            ledger.head,
            intent_state,
            parent_version,
        )

    @property
    def rule(self) -> list:
        return json.loads(self.rule_json)

    def sealed_hash(self) -> str:
        """D7: hash over everything a binding repair must NOT change. Excludes the free-text summary
        and the version number (a binding repair keeps the concept version anyway)."""
        return sha(
            {
                "rule": self.rule,
                "input_schema": self.input_schema,
                "preservation": list(self.preservation_constraints),
                "domain": self.domain_hash,
                "ledger": self.ledger_hash,
            }
        )


FORBIDDEN_KEYS = {"confidence", "verified", "score", "reliability", "probability"}


def assert_no_aggregate_confidence(payload: Any, path: str = "") -> None:
    """Contract helper: no serialised object may carry a merged confidence/verified field (spec 7.5)."""
    if isinstance(payload, dict):
        for k, v in payload.items():
            if str(k).lower() in FORBIDDEN_KEYS:
                raise AssertionError(f"aggregate evidence field {path}{k!r} is prohibited")
            assert_no_aggregate_confidence(v, f"{path}{k}.")
    elif isinstance(payload, (list, tuple)):
        for i, v in enumerate(payload):
            assert_no_aggregate_confidence(v, f"{path}{i}.")
