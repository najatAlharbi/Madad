"""GET /api/health — is this backend able to serve forecasts?

Wraps app.ml.health.get_health() so the same report is available from the
command line (`python -m app.ml.health`) and over HTTP.
"""

from fastapi import APIRouter

from app.ml.health import get_health

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Report artifact presence, feature count, trained months, last
    evaluation metrics, library versions and uptime.

    Returns 200 even when artifacts are missing — the payload's "status"
    field carries "ok" or "degraded" so a caller can tell the difference
    without treating an un-trained backend as a transport failure.
    """
    return get_health()
