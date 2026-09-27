"""Run the models and serve the result.

  POST /api/forecast/run      build features -> predict -> rules -> store on session
  GET  /api/forecast/results  the stored run
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import require_forecast, require_session, runtime_dep
from app.core.runtime import Runtime
from app.core.session_store import Session, store
from app.ml.pipeline import run_forecast

logger = logging.getLogger("madad.forecast")

router = APIRouter(tags=["forecast"])


class ForecastRequest(BaseModel):
    forecast_month: str | None = None
    facility_id: int | None = None


@router.post("/forecast/run")
def run(
    body: ForecastRequest,
    session: Session = Depends(require_session),
    runtime: Runtime = Depends(runtime_dep),
) -> dict:
    """Forecast next month for the session's facility.

    Uses the session's uploaded month when present, otherwise forecasts from
    stored history alone. Replaces any previous run and clears chat history,
    so an answer can never mix numbers from two runs.
    """
    facility_id = body.facility_id or session.facility_id
    if facility_id is None:
        raise HTTPException(
            status_code=409,
            detail={"error": "no_facility", "message": "Upload a month or load the demo facility first."},
        )

    uploaded = session.uploaded_df
    month = body.forecast_month
    if month is None and uploaded is not None and not uploaded.empty:
        # Forecast the month right after the uploaded one.
        month = str(uploaded["date_parsed"].max().to_period("M") + 1)
    month = month or runtime.default_forecast_month

    try:
        payload = run_forecast(runtime, facility_id, month, uploaded=uploaded, is_demo=session.is_demo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": "forecast_failed", "message": str(exc)}) from exc

    store.reset_forecast(session)
    session.forecast_run = payload
    session.facility_id = facility_id

    return payload


@router.get("/forecast/results")
def results(session: Session = Depends(require_session)) -> dict:
    """Return the stored forecast run, or 409 if there isn't one."""
    return require_forecast(session)
