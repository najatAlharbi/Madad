"""POST /api/session — create or refresh a session and record the chosen view."""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Response
from pydantic import BaseModel, Field

from app.api.deps import set_session_cookie
from app.core.session_store import SessionExpired, store

router = APIRouter(tags=["session"])

VALID_ROLES = {"warehouse", "authority"}


class SessionRequest(BaseModel):
    role: str | None = Field(default=None, description="'warehouse' or 'authority'")
    facility_id: int | None = Field(default=None, description="Warehouse view: which facility")


@router.post("/session")
def create_or_refresh(
    body: SessionRequest,
    response: Response,
    madad_session: str | None = Cookie(default=None),
) -> dict:
    """Create a session, or refresh the existing one and update its role.

    Called by the landing page when the visitor picks a workspace. Safe to
    call repeatedly: an unknown or expired cookie simply yields a new session
    rather than an error, because picking a workspace should never fail.
    """
    if body.role is not None and body.role not in VALID_ROLES:
        return {"error": "invalid_role", "message": f"role must be one of {sorted(VALID_ROLES)}"}

    session, created = store.get_or_create(madad_session, body.role)

    if body.role:
        session.role = body.role
    if body.facility_id is not None:
        session.facility_id = body.facility_id

    set_session_cookie(response, session.session_id)
    return {**session.to_public(), "created": created}


@router.get("/session")
def read_session(madad_session: str | None = Cookie(default=None)) -> dict:
    """Report the current session without creating one.

    Returns ``{"active": false}`` rather than 410 so the frontend can decide
    where to send a first-time visitor without treating it as an error.
    """
    try:
        return {"active": True, **store.get(madad_session).to_public()}
    except SessionExpired:
        return {"active": False}


@router.delete("/session")
def end_session(response: Response, madad_session: str | None = Cookie(default=None)) -> dict:
    """Drop the session (used by 'switch workspace')."""
    store.delete(madad_session)
    response.delete_cookie("madad_session", path="/")
    return {"active": False}
