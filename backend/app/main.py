"""Madad FastAPI application.

Run from backend/:
    uvicorn app.main:app --reload --port 8000

Startup loads the models, the panel and the precomputed aggregate tables
once (app/core/runtime.py). Nothing is trained or recomputed per request.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import authority, chat, forecast, health, session, transfers, upload
from app.core.config import CORS_ORIGINS, GROQ_MODEL, MODELS_DIR
from app.core.runtime import load_runtime
from app.core.session_store import store
from app.llm import chat as chat_engine
from app.ml.health import ARTIFACT_FILES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("madad")

SESSION_SWEEP_SECONDS = 300


async def _sweep_sessions_forever() -> None:
    """Drop timed-out sessions every few minutes."""
    while True:
        await asyncio.sleep(SESSION_SWEEP_SECONDS)
        try:
            store.sweep()
        except Exception:  # a sweep failure must not kill the loop
            logger.exception("session sweep failed")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Load everything once, then start the session sweeper.

    A missing artifact is logged rather than raised so /api/health stays
    reachable and can explain why the backend cannot forecast.
    """
    missing = [name for name in ARTIFACT_FILES if not (MODELS_DIR / name).exists()]
    if missing:
        logger.warning("model artifacts MISSING in %s: %s — run `python -m app.ml.train`", MODELS_DIR, missing)
    else:
        try:
            load_runtime()
        except Exception:
            logger.exception("runtime failed to load — /api/health will report the problem")

    logger.info(
        "chat: provider=groq model=%s configured=%s",
        GROQ_MODEL,
        chat_engine.is_configured(),
    )

    sweeper = asyncio.create_task(_sweep_sessions_forever())
    try:
        yield
    finally:
        sweeper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sweeper


app = FastAPI(
    title="Madad API",
    description="Medical logistics decision support: forecast, detect, redistribute, explain.",
    version="1.0.0",
    lifespan=lifespan,
)

# Only needed if the frontend is served from its own origin. In development
# the Vite dev server proxies /api to this process, so the browser sees a
# single origin and the session cookie travels without a CORS exemption.
# allow_credentials with an explicit origin list (never "*") is what lets the
# cookie through if that proxy is removed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    health.router,
    session.router,
    upload.router,
    forecast.router,
    transfers.router,
    authority.router,
    chat.router,
):
    app.include_router(router, prefix="/api")


@app.exception_handler(500)
async def internal_error(_request, exc: Exception) -> JSONResponse:
    """Return a shaped error the UI can display instead of a bare 500."""
    logger.exception("unhandled error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": {"error": "internal_error", "message": "Something went wrong on the server."}},
    )
