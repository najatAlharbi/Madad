"""Shared FastAPI dependencies: the session cookie and the runtime cache."""

from __future__ import annotations

from fastapi import Cookie, HTTPException, Response

from app.core.config import SESSION_TTL_MINUTES
from app.core.runtime import Runtime, get_runtime
from app.core.session_store import Session, SessionExpired, store

SESSION_COOKIE = "madad_session"


def set_session_cookie(response: Response, session_id: str) -> None:
    """Issue the session cookie.

    HttpOnly so no script can read it, SameSite=Lax so it still travels on
    top-level navigation. secure=False because the MVP runs on http://localhost;
    set it to True behind TLS.
    """
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=SESSION_TTL_MINUTES * 60,
        path="/",
    )


def require_session(madad_session: str | None = Cookie(default=None)) -> Session:
    """Resolve the caller's session or fail with 410.

    410 Gone (not 401) is deliberate: the session genuinely existed and is
    now irrecoverable, which is exactly what the UI needs to distinguish
    "log in again" from "your work is gone, re-run the forecast".
    """
    try:
        return store.get(madad_session)
    except SessionExpired as exc:
        raise HTTPException(status_code=410, detail={"error": "session_expired", "message": str(exc)}) from exc


def require_forecast(session: Session) -> dict:
    """The session's forecast run, or a 409 telling the UI to run one."""
    if not session.forecast_run:
        raise HTTPException(
            status_code=409,
            detail={"error": "no_forecast", "message": "Run a forecast first."},
        )
    return session.forecast_run


def runtime_dep() -> Runtime:
    return get_runtime()
