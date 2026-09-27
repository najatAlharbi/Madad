"""In-memory session store. No database, by design.

Sessions hold a user's uploaded month, their forecast run and their chat
history for 60 minutes of inactivity. Restarting the backend wipes them —
that is intentional and the UI is built to recover from it (every endpoint
returns HTTP 410 ``session_expired`` and the frontend offers a way back).

Thread-safe: uvicorn runs sync endpoint functions in a worker threadpool,
so every read and write takes the lock.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.config import SESSION_MAX_CHAT_TURNS, SESSION_MAX_COUNT, SESSION_TTL_MINUTES

logger = logging.getLogger("madad.sessions")


class SessionExpired(Exception):
    """Raised when a session id is unknown or has aged out."""


@dataclass
class Session:
    """One visitor's server-side state."""

    session_id: str
    created: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    role: str | None = None                 # "warehouse" | "authority"
    facility_id: int | None = None
    is_demo: bool = False
    uploaded_df: Any = None                 # pandas DataFrame of the month
    upload_meta: dict | None = None         # month, row count, validation report
    forecast_run: dict | None = None        # the served forecast payload
    transfer_plan: dict | None = None
    chat_history: list[dict] = field(default_factory=list)
    chat_summary: str | None = None         # running line kept when turns are dropped

    def touch(self) -> None:
        self.last_seen = time.time()

    def to_public(self) -> dict:
        """The shape /api/session returns — never the DataFrames."""
        return {
            "session_id": self.session_id,
            "role": self.role,
            "facility_id": self.facility_id,
            "is_demo": self.is_demo,
            "has_upload": self.uploaded_df is not None,
            "has_forecast": self.forecast_run is not None,
            "chat_turns": len(self.chat_history),
            "created": self.created,
            "last_seen": self.last_seen,
        }


class SessionStore:
    """Dict of session_id -> Session with a TTL and an LRU cap."""

    def __init__(
        self,
        ttl_minutes: int = SESSION_TTL_MINUTES,
        max_sessions: int = SESSION_MAX_COUNT,
        max_chat_turns: int = SESSION_MAX_CHAT_TURNS,
    ) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()
        self.ttl_seconds = ttl_minutes * 60
        self.max_sessions = max_sessions
        self.max_chat_turns = max_chat_turns

    def create(self, role: str | None = None) -> Session:
        """Mint a session with a cryptographically random id."""
        session = Session(session_id=secrets.token_urlsafe(32), role=role)
        with self._lock:
            self._evict_if_full_locked()
            self._sessions[session.session_id] = session
        logger.info("session created (role=%s, live=%d)", role, len(self._sessions))
        return session

    def get(self, session_id: str | None) -> Session:
        """Fetch and touch a live session, or raise SessionExpired."""
        if not session_id:
            raise SessionExpired("no session cookie")
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise SessionExpired("unknown session")
            if time.time() - session.last_seen > self.ttl_seconds:
                del self._sessions[session_id]
                raise SessionExpired("session timed out")
            session.touch()
            return session

    def get_or_create(self, session_id: str | None, role: str | None = None) -> tuple[Session, bool]:
        """Return (session, created_now). Used by /api/session, which must
        work whether or not the caller already has a cookie."""
        try:
            return self.get(session_id), False
        except SessionExpired:
            return self.create(role), True

    def append_chat(self, session: Session, role: str, content: str) -> None:
        """Add a chat turn, trimming the oldest and keeping a summary line.

        The summary exists so a long conversation still carries a hint of
        what came before the window, without unbounded prompt growth.
        """
        with self._lock:
            session.chat_history.append({"role": role, "content": content, "at": time.time()})
            overflow = len(session.chat_history) - self.max_chat_turns
            if overflow > 0:
                dropped = session.chat_history[:overflow]
                del session.chat_history[:overflow]
                first_user = next((d["content"] for d in dropped if d["role"] == "user"), None)
                if first_user:
                    session.chat_summary = (
                        f"Earlier in this conversation the user asked about: {first_user[:160]}"
                    )

    def reset_forecast(self, session: Session) -> None:
        """A new forecast run replaces the old context and clears chat, so an
        answer can never mix numbers from two different runs."""
        with self._lock:
            session.forecast_run = None
            session.transfer_plan = None
            session.chat_history = []
            session.chat_summary = None

    def delete(self, session_id: str | None) -> bool:
        """Drop a session immediately (used by 'switch workspace')."""
        if not session_id:
            return False
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def sweep(self) -> int:
        """Drop timed-out sessions. Returns how many went."""
        cutoff = time.time() - self.ttl_seconds
        with self._lock:
            stale = [sid for sid, s in self._sessions.items() if s.last_seen < cutoff]
            for sid in stale:
                del self._sessions[sid]
        if stale:
            logger.info("swept %d expired session(s), %d live", len(stale), len(self._sessions))
        return len(stale)

    def _evict_if_full_locked(self) -> None:
        """Make room by dropping the least-recently-seen session."""
        while len(self._sessions) >= self.max_sessions:
            oldest = min(self._sessions.values(), key=lambda s: s.last_seen)
            del self._sessions[oldest.session_id]
            logger.info("evicted LRU session (cap %d reached)", self.max_sessions)

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)


# One store per process.
store = SessionStore()
