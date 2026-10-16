from fractions import Fraction as F

import pytest

from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching.accounting import Ledger, OverBudget


def test_each_attempt_counts_in_exactly_one_category(tmp_path):
    L = Ledger(LocalStore(tmp_path), cap_usd=F(1))
    L.reserve("a1", "act", F(1, 10))
    assert L.exposure() == {"settled": 0, "reserved": F(1, 10), "uncertain": 0, "total": F(1, 10)}
    L.dispatched("a1")
    assert L.exposure()["reserved"] == 0 and L.exposure()["uncertain"] == F(1, 10)
    L.settle("a1", F(3, 100))
    assert L.exposure() == {"settled": F(3, 100), "reserved": 0, "uncertain": 0, "total": F(3, 100)}


def test_crash_after_dispatch_keeps_worst_case_exposure(tmp_path):
    L = Ledger(LocalStore(tmp_path), cap_usd=F(1))
    L.reserve("a1", "act", F(1, 10))
    L.dispatched("a1")
    L.mark_unknown("a1")
    assert L.state("a1") == "outcome_unknown" and L.exposure()["uncertain"] == F(1, 10)


def test_reservation_is_refused_over_cap(tmp_path):
    L = Ledger(LocalStore(tmp_path), cap_usd=F(1, 10))
    L.reserve("a1", "act", F(1, 10))
    with pytest.raises(OverBudget):
        L.reserve("a2", "act", F(1, 100))


def test_duplicate_reserve_is_idempotent(tmp_path):
    L = Ledger(LocalStore(tmp_path), cap_usd=F(1))
    L.reserve("a1", "act", F(1, 10))
    L.reserve("a1", "act", F(1, 10))
    assert L.exposure()["reserved"] == F(1, 10)


def test_two_ledgers_on_one_store_share_state(tmp_path):
    s = LocalStore(tmp_path)
    Ledger(s, F(1)).reserve("a1", "act", F(1, 2))
    with pytest.raises(OverBudget):
        Ledger(s, F(1)).reserve("a2", "act", F(3, 5))


def test_exposure_can_be_limited_to_one_sessions_actions(tmp_path):
    from fractions import Fraction as F

    from open_apprentice.storage.store import LocalStore
    from open_apprentice.teaching.accounting import Ledger

    led = Ledger(LocalStore(tmp_path), F(5))
    led.reserve("a1", "act-mine", F(1, 5))
    led.reserve("a2", "act-other", F(1, 5))
    led.dispatched("a1")
    led.settle("a1", F(1, 10))
    mine = led.exposure({"act-mine"})
    assert mine == {"settled": F(1, 10), "reserved": 0, "uncertain": 0, "total": F(1, 10)}
    assert led.exposure()["total"] == F(3, 10)
