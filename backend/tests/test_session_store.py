"""Session store: TTL, LRU eviction, chat trimming, forecast reset."""

import time

import pytest

from app.core.session_store import SessionExpired, SessionStore


def test_create_and_get_round_trip():
    store = SessionStore()
    session = store.create(role="warehouse")
    assert store.get(session.session_id) is session
    assert session.role == "warehouse"
    # Ids must be unguessable, not sequential.
    assert len(session.session_id) >= 32


def test_unknown_session_raises():
    store = SessionStore()
    with pytest.raises(SessionExpired):
        store.get("not-a-real-session")
    with pytest.raises(SessionExpired):
        store.get(None)


def test_session_times_out():
    store = SessionStore(ttl_minutes=0)
    session = store.create()
    time.sleep(0.01)
    with pytest.raises(SessionExpired):
        store.get(session.session_id)


def test_get_refreshes_last_seen():
    store = SessionStore()
    session = store.create()
    original = session.last_seen
    time.sleep(0.01)
    store.get(session.session_id)
    assert session.last_seen > original


def test_lru_eviction_at_cap():
    store = SessionStore(max_sessions=3)
    first = store.create()
    time.sleep(0.01)
    second = store.create()
    time.sleep(0.01)
    store.create()

    # Touch the oldest so the *second* becomes least-recently-seen.
    store.get(first.session_id)
    time.sleep(0.01)
    store.create()

    assert len(store) == 3
    assert store.get(first.session_id) is first
    with pytest.raises(SessionExpired):
        store.get(second.session_id)


def test_chat_history_trims_and_keeps_a_summary():
    store = SessionStore(max_chat_turns=4)
    session = store.create()

    store.append_chat(session, "user", "first question about folic acid")
    for index in range(6):
        store.append_chat(session, "assistant", f"answer {index}")

    assert len(session.chat_history) == 4
    assert session.chat_summary is not None
    assert "folic acid" in session.chat_summary


def test_reset_forecast_clears_chat():
    """A new run must not leave answers grounded in the previous one."""
    store = SessionStore()
    session = store.create()
    session.forecast_run = {"products": []}
    session.transfer_plan = {"suggestions": []}
    store.append_chat(session, "user", "old question")

    store.reset_forecast(session)

    assert session.forecast_run is None
    assert session.transfer_plan is None
    assert session.chat_history == []
    assert session.chat_summary is None


def test_sweep_removes_only_expired():
    store = SessionStore(ttl_minutes=0)
    store.create()
    assert store.sweep() == 1
    assert len(store) == 0


def test_delete_is_idempotent():
    store = SessionStore()
    session = store.create()
    assert store.delete(session.session_id) is True
    assert store.delete(session.session_id) is False
