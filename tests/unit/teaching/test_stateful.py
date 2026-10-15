"""Generated action sequences against the event log, the exposure ledger and skill versions (spec 9 B)."""

import tempfile
from fractions import Fraction as F

from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from open_apprentice.skills.versions import ActivationRejected, SkillStore
from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching import codec
from open_apprentice.teaching.accounting import Ledger, OverBudget
from open_apprentice.teaching.events import Conflict, SessionLog


class EventLogMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.store = LocalStore(tempfile.mkdtemp())
        self.log = SessionLog(self.store, "s")
        self.log.create(owner="o")
        self.expected: list[str] = []
        self.orphans = 0

    @rule(t=st.sampled_from(["SceneRegistered", "ActionIssued", "ResponseRecorded"]))
    def append(self, t):
        self.expected.append(self.log.append(t, "system", {"n": len(self.expected)}).event_id)

    @rule()
    def crash_before_manifest(self):
        self.orphans += 1
        orphan = {
            "event_id": f"orphan{self.orphans}",
            "prev_event_id": None,
            "seq": 99,
            "type": "X",
            "origin": "system",
            "payload": {},
            "caused_by": None,
        }
        self.store.create(f"sessions/s/events/{orphan['event_id']}.json", codec.dumps(orphan))

    @rule()
    def stale_writer_loses(self):
        rev = self.log.manifest()[0]["manifest_revision"]
        self.expected.append(
            SessionLog(self.store, "s")
            .append("ActionIssued", "system", {}, expected_revision=rev)
            .event_id
        )
        try:
            self.log.append("ActionIssued", "system", {}, expected_revision=rev)
        except Conflict:
            return
        raise AssertionError("a stale writer must lose")

    @invariant()
    def replay_is_the_committed_chain(self):
        evs = self.log.events()
        assert [e.event_id for e in evs] == self.expected
        assert [e.seq for e in evs] == list(range(1, len(evs) + 1))


class LedgerMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.ledger = Ledger(LocalStore(tempfile.mkdtemp()), F(1))
        self.states: dict[str, str] = {}
        self.n = 0

    @rule(worst=st.fractions(min_value=F(1, 100), max_value=F(1, 3), max_denominator=100))
    def reserve(self, worst):
        self.n += 1
        aid = f"a{self.n}"
        try:
            self.ledger.reserve(aid, "act", worst)
            self.states[aid] = "reserved"
        except OverBudget:
            pass

    @precondition(lambda self: any(s == "reserved" for s in self.states.values()))
    @rule(data=st.data())
    def dispatch_or_release(self, data):
        aid = data.draw(
            st.sampled_from(sorted(a for a, s in self.states.items() if s == "reserved"))
        )
        if data.draw(st.booleans()):
            self.ledger.dispatched(aid)
            self.states[aid] = "dispatched"
        else:
            self.ledger.fail_before_dispatch(aid)
            self.states[aid] = "released"

    @precondition(lambda self: any(s == "dispatched" for s in self.states.values()))
    @rule(
        data=st.data(), actual=st.fractions(min_value=F(0), max_value=F(1, 3), max_denominator=100)
    )
    def settle_or_lose(self, data, actual):
        aid = data.draw(
            st.sampled_from(sorted(a for a, s in self.states.items() if s == "dispatched"))
        )
        if data.draw(st.booleans()):
            self.ledger.settle(aid, actual)
            self.states[aid] = "completed"
        else:
            self.ledger.mark_unknown(aid)
            self.states[aid] = "outcome_unknown"

    @invariant()
    def one_state_each_and_totals_add_up(self):
        for aid, s in self.states.items():
            assert self.ledger.state(aid) == s
        e = self.ledger.exposure()
        assert e["total"] == e["settled"] + e["reserved"] + e["uncertain"]


class VersionMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.skills = SkillStore(LocalStore(tempfile.mkdtemp()))
        self.stored = 0
        self.ops = 0

    @rule(tag=st.integers(0, 5))
    def store(self, tag):
        v = self.skills.store_version(
            "k", {"skill_id": "k", "program": {"rule": [tag]}, "evidence": [], "superseded": {}}
        )
        self.stored = max(self.stored, v)

    @precondition(lambda self: self.stored > 0)
    @rule(data=st.data(), stale=st.booleans())
    def activate(self, data, stale):
        v = data.draw(st.integers(1, self.stored))
        g = self.skills.active("k")[2]
        self.ops += 1
        try:
            self.skills.activate("k", v, (g or 0) + 7 if stale else g, f"op{self.ops}", "s")
            assert not stale
        except ActivationRejected:
            assert stale

    @invariant()
    def pointer_references_a_stored_version_and_history_ends_there(self):
        v = self.skills.active("k")[0]
        if v is None:
            return
        self.skills.version("k", v)
        h = self.skills.history("k")
        assert h and h[-1]["to_version"] == v
        for a, b in zip(h, h[1:]):
            assert b["from_version"] == a["to_version"]


TestEventLog = EventLogMachine.TestCase
TestLedger = LedgerMachine.TestCase
TestVersions = VersionMachine.TestCase
