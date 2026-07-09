"""
Unit tesztek az `app.presence` modulra.

A `PresenceTracker` egy fake clock-kal tesztelhető — nem kell tényleges
másodperceket várni.
"""
import pytest

from app.presence import PresenceTracker


class FakeClock:
    def __init__(self, t0: float = 1_700_000_000.0):
        self.t = t0
    def __call__(self):
        return self.t
    def advance(self, seconds: float):
        self.t += seconds


@pytest.fixture
def tracker():
    clock = FakeClock()
    t = PresenceTracker(expire_seconds=60, clock=clock)
    t._clock_obj = clock  # tesztek elérhessék
    return t


def test_empty_tracker_returns_no_users(tracker):
    assert tracker.active_users("x", "y") == []


def test_heartbeat_registers_user(tracker):
    tracker.heartbeat("Bakonykuti", "sample", "anna")
    users = tracker.active_users("Bakonykuti", "sample")
    assert len(users) == 1
    assert users[0][0] == "anna"


def test_multiple_users_on_same_file(tracker):
    tracker.heartbeat("Bakonykuti", "sample", "anna")
    tracker.heartbeat("Bakonykuti", "sample", "bela")
    users = dict(tracker.active_users("Bakonykuti", "sample"))
    assert set(users.keys()) == {"anna", "bela"}


def test_heartbeat_refreshes_timestamp(tracker):
    tracker.heartbeat("x", "y", "anna")
    first_ts = tracker.active_users("x", "y")[0][1]
    tracker._clock_obj.advance(10)
    tracker.heartbeat("x", "y", "anna")
    second_ts = tracker.active_users("x", "y")[0][1]
    assert second_ts > first_ts


def test_expiration_removes_stale_user(tracker):
    tracker.heartbeat("x", "y", "anna")
    tracker._clock_obj.advance(61)  # túl az expire_seconds-en
    assert tracker.active_users("x", "y") == []


def test_expiration_partial(tracker):
    """Egy user friss, másik lejárt — csak a friss maradjon."""
    tracker.heartbeat("x", "y", "anna")
    tracker._clock_obj.advance(30)
    tracker.heartbeat("x", "y", "bela")
    tracker._clock_obj.advance(40)  # anna most 70 mp-e, bela 40 mp-e
    users = dict(tracker.active_users("x", "y"))
    assert "anna" not in users
    assert "bela" in users


def test_leave_removes_user(tracker):
    tracker.heartbeat("x", "y", "anna")
    tracker.heartbeat("x", "y", "bela")
    tracker.leave("x", "y", "anna")
    users = dict(tracker.active_users("x", "y"))
    assert set(users.keys()) == {"bela"}


def test_leave_missing_ok(tracker):
    # Nem szabad hibáznia
    tracker.leave("x", "y", "nincsilyen")


def test_snapshot_returns_all_fresh(tracker):
    tracker.heartbeat("A", "a", "anna")
    tracker.heartbeat("B", "b", "bela")
    snap = tracker.snapshot()
    assert "A/a" in snap
    assert "B/b" in snap


def test_key_normalisation(tracker):
    """Trailing/leading slash-ok normalizálódnak."""
    tracker.heartbeat("/Bakonykuti/", "sample", "anna")
    assert len(tracker.active_users("Bakonykuti", "sample")) == 1


def test_empty_path_key(tracker):
    tracker.heartbeat("", "root_pair", "anna")
    users = tracker.active_users("", "root_pair")
    assert users[0][0] == "anna"
