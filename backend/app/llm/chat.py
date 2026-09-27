"""The Madad assistant: answers questions from the session's own numbers.

Grounding, not retrieval-by-embedding. At this size the whole forecast run
fits in the prompt, so "retrieval" is just: compact the run to JSON, add the
transfer suggestions and the network summary, and trim to a byte budget by
keeping the products the question mentions plus the largest gaps.

Two hard rules the system prompt enforces and this module supports:
- the model may only use the supplied context, and
- if the key is missing we return a labelled error instead of an answer.
  Nothing here ever fabricates a number.
"""

from __future__ import annotations

import json
import logging
import re
import time

from app.core.config import (
    CHAT_CONTEXT_BUDGET_BYTES,
    CHAT_HISTORY_TURNS,
    CHAT_MAX_TOKENS,
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_REASONING_EFFORT,
)

logger = logging.getLogger("madad.chat")

# Keep this many of the biggest gaps when the full context is too large.
LARGEST_GAPS_KEPT = 10

SYSTEM_PROMPT = """You are Madad's assistant. Madad forecasts monthly medical supply \
consumption for hospital warehouses and suggests transfers between them.

Rules you must follow:
- Answer ONLY from the CONTEXT provided in this conversation. Never invent or \
estimate a number that is not there.
- If the context does not contain the answer, say exactly what is missing and \
suggest where the user can find it in the app. Do not guess.
- Always state units ("units") and the month the numbers refer to.
- Keep answers under 150 words. Lead with the answer, then the numbers.
- The CONTEXT is always written in English, but the user may write in Arabic. \
A question in Arabic about the same supplies, stock, forecasts, shortages or \
transfers IS answerable from the English context — translate it yourself and \
answer normally. Never refuse a question just because it is not in English.
- Reply in the same language the user wrote in: Arabic question, Arabic answer; \
English question, English answer. Keep product names as they appear in the context.
- Write plain prose. Do not use markdown bold, headings or bullet symbols, and \
do not insert unusual spacing characters between numbers and units.
- P50 is the expected demand, P90 is the conservative planning demand, and the \
gap is P90 minus stock on hand. Status: critical means stock is below P50, \
at risk means stock is between P50 and P90, surplus means stock is at or above P90.
- You are advisory. Do not give clinical or prescribing advice."""


class LLMNotConfigured(Exception):
    """Raised when no Groq API key is present."""


def _clean_answer(text: str) -> str:
    """Normalise model output for display.

    Models emit markdown emphasis and exotic Unicode spacing (U+202F narrow
    no-break space between a number and its unit) whatever the prompt says.
    The UI renders plain text, so strip it here rather than relying on the
    model to comply.
    """
    for exotic, plain in ((" ", " "), (" ", " "), (" ", " "), ("‑", "-")):
        text = text.replace(exotic, plain)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)      # bold
    text = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", text)  # italics
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)          # headings
    text = re.sub(r"^\s*[-•]\s+", "- ", text, flags=re.MULTILINE)       # bullet glyphs
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def is_configured() -> bool:
    return bool(GROQ_API_KEY)


def _compact_forecast(forecast_run: dict, question: str) -> tuple[dict, list[str]]:
    """Shrink a forecast run to what the question plausibly needs.

    Returns (context_fragment, used_context_keys). The keys describe what the
    answer was actually grounded in, computed here rather than asked of the
    model — the server knows what it sent, so it does not need to trust a
    self-report.
    """
    products = forecast_run.get("products", [])
    lowered = question.lower()

    def mentioned(product: dict) -> bool:
        name = str(product.get("name", "")).lower()
        first_word = re.split(r"[ ,(]", name)[0]
        return bool(first_word) and len(first_word) > 3 and first_word in lowered

    def compact(product: dict) -> dict:
        return {
            "product": product["name"],
            "stock": product["stock"],
            "p10": product["p10"],
            "p50": product["p50"],
            "p90": product["p90"],
            "status": product["severity"],
            "gap_units": product["gap"],
        }

    full = [compact(p) for p in products]
    fragment = {
        "facility": forecast_run.get("facility"),
        "forecast_month": forecast_run.get("forecast_month"),
        "counts": forecast_run.get("counts"),
        "products": full,
    }
    keys = ["forecast_run"]

    if len(json.dumps(fragment).encode()) <= CHAT_CONTEXT_BUDGET_BYTES:
        return fragment, keys

    # Too big: keep what was asked about plus the biggest gaps.
    asked = [p for p in products if mentioned(p)]
    biggest = sorted(products, key=lambda p: -p["gap"])[:LARGEST_GAPS_KEPT]
    chosen, seen = [], set()
    for product in asked + biggest:
        if product["product_id"] not in seen:
            seen.add(product["product_id"])
            chosen.append(product)

    fragment["products"] = [compact(p) for p in chosen]
    fragment["note"] = (
        f"Showing {len(chosen)} of {len(products)} supplies: those asked about plus the largest gaps."
    )
    keys.append("forecast_run.filtered")
    return fragment, keys


def build_context(
    forecast_run: dict | None,
    transfer_plan: dict | None,
    network_summary: dict | None,
    question: str,
) -> tuple[str, list[str]]:
    """Assemble the grounding context and the list of keys it came from."""
    context: dict = {}
    used: list[str] = []

    if forecast_run:
        fragment, keys = _compact_forecast(forecast_run, question)
        context["forecast"] = fragment
        used.extend(keys)

    if transfer_plan and transfer_plan.get("suggestions"):
        context["transfer_suggestions"] = transfer_plan["suggestions"][:15]
        used.append("transfer_plan")

    if network_summary:
        context["network"] = network_summary
        used.append("network_summary")

    if not context:
        context["note"] = "No forecast has been run in this session yet."

    return json.dumps(context, ensure_ascii=False, default=str), used


def answer(
    question: str,
    forecast_run: dict | None = None,
    transfer_plan: dict | None = None,
    network_summary: dict | None = None,
    history: list[dict] | None = None,
    history_summary: str | None = None,
) -> dict:
    """Answer one question against the session's numbers.

    Raises:
        LLMNotConfigured: when GROQ_API_KEY is unset. The caller turns this
            into a labelled API error; we never substitute a fake answer.
    """
    if not is_configured():
        raise LLMNotConfigured("GROQ_API_KEY is not set")

    from groq import Groq  # imported lazily so the app starts without the key

    context_json, used_keys = build_context(forecast_run, transfer_plan, network_summary, question)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history_summary:
        messages.append({"role": "system", "content": history_summary})
    messages.append({"role": "system", "content": f"CONTEXT (the only facts you may use):\n{context_json}"})

    for turn in (history or [])[-CHAT_HISTORY_TURNS:]:
        if turn.get("role") in ("user", "assistant"):
            messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": question})

    client = Groq(api_key=GROQ_API_KEY)
    started = time.perf_counter()

    kwargs: dict = {
        "model": GROQ_MODEL,
        "messages": messages,
        "max_tokens": CHAT_MAX_TOKENS,
        "temperature": 0.2,
    }
    # The gpt-oss models reason before answering and will spend the whole
    # budget thinking unless the reasoning pass is capped.
    if "gpt-oss" in GROQ_MODEL:
        kwargs["reasoning_effort"] = GROQ_REASONING_EFFORT

    response = client.chat.completions.create(**kwargs)
    elapsed = time.perf_counter() - started

    text = _clean_answer(response.choices[0].message.content or "")
    if not text:
        text = "I could not produce an answer for that. Try asking about a specific supply."

    # Never log the key or the full prompt — only shape and cost.
    logger.info(
        "chat model=%s context_bytes=%d in=%s out=%s %.2fs",
        GROQ_MODEL, len(context_json), response.usage.prompt_tokens, response.usage.completion_tokens, elapsed,
    )

    return {
        "answer": text,
        "used_context_keys": used_keys,
        "model": GROQ_MODEL,
        "elapsed_seconds": round(elapsed, 2),
    }
