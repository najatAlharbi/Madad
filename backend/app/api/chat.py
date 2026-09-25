"""POST /api/chat — grounded answers about the session's own forecast."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import require_session, runtime_dep
from app.core.runtime import Runtime
from app.core.session_store import Session, store
from app.llm import chat as chat_engine

logger = logging.getLogger("madad.chat.api")

router = APIRouter(tags=["chat"])

SUGGESTED_QUESTIONS = [
    "What should I order first this month?",
    "Why is folic acid critical?",
    "Which warehouse is closest for my biggest shortage?",
    "What does the P10–P90 range mean here?",
]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


@router.get("/chat/history")
def history(session: Session = Depends(require_session)) -> dict:
    """The visible turns, plus what the assistant is allowed to look at."""
    return {
        "history": [
            {"role": turn["role"], "content": turn["content"], "at": turn["at"]}
            for turn in session.chat_history
        ],
        "summary": session.chat_summary,
        "configured": chat_engine.is_configured(),
        "model": chat_engine.GROQ_MODEL if chat_engine.is_configured() else None,
        "suggested_questions": SUGGESTED_QUESTIONS,
        "can_look_up": {
            "forecast_run": session.forecast_run is not None,
            "transfer_plan": session.transfer_plan is not None,
            "network_summary": True,
        },
    }


@router.post("/chat")
def send(
    body: ChatRequest,
    session: Session = Depends(require_session),
    runtime: Runtime = Depends(runtime_dep),
) -> dict:
    """Answer a question using only this session's numbers.

    Returns 503 with a labelled error when no API key is configured — the
    endpoint never substitutes a canned or invented answer.
    """
    if not chat_engine.is_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "llm_not_configured",
                "message": "The assistant is not configured. Add GROQ_API_KEY to backend/.env and restart.",
            },
        )

    network_summary = None
    overview = runtime.authority.get("overview")
    if overview:
        network_summary = {
            "period": overview.get("period") or overview.get("forecast_month"),
            "redistribution": overview.get("redistribution"),
            "status_counts": overview.get("status_counts"),
        }

    try:
        result = chat_engine.answer(
            question=body.message,
            forecast_run=session.forecast_run,
            transfer_plan=session.transfer_plan,
            network_summary=network_summary,
            history=session.chat_history,
            history_summary=session.chat_summary,
        )
    except chat_engine.LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail={"error": "llm_not_configured", "message": str(exc)}) from exc
    except Exception as exc:
        # Upstream failure (rate limit, network, model retired). Surface it
        # rather than inventing an answer.
        logger.exception("chat upstream failure")
        raise HTTPException(
            status_code=502,
            detail={"error": "llm_request_failed", "message": f"{type(exc).__name__}: {exc}"},
        ) from exc

    store.append_chat(session, "user", body.message)
    store.append_chat(session, "assistant", result["answer"])

    return result
