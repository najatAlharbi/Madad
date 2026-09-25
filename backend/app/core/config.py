"""Central path configuration for the Madad forecasting pipeline.

All paths are resolved relative to the repository root and can be
overridden via environment variables (optionally set in a `.env` file).
No other module in this project should hard-code a path — import from
here instead.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[3]

# The archive's own zip entry is named "Madad_Integrated_Data.csv ✰"
# (a trailing space + star baked into the filename inside the zip itself,
# not something scripts/unpack_data.py added) — see docs/data_profile.md.
RAW_DATA = Path(
    os.getenv("RAW_DATA", REPO_ROOT / "data" / "raw" / "Madad_Integrated_Data.csv ✰")
).resolve()
RAW_FORMAT = os.getenv("RAW_FORMAT", "csv")
PANEL_PARQUET = Path(
    os.getenv("PANEL_PARQUET", REPO_ROOT / "data" / "processed" / "panel.parquet")
).resolve()
MODELS_DIR = Path(os.getenv("MODELS_DIR", REPO_ROOT / "models")).resolve()
REPORTS_DIR = Path(os.getenv("REPORTS_DIR", REPO_ROOT / "reports")).resolve()
NOTEBOOKS_DIR = Path(
    os.getenv("NOTEBOOKS_DIR", REPO_ROOT / "Madad_Models_Notebooks")
).resolve()
FACILITIES_PARQUET = Path(
    os.getenv("FACILITIES_PARQUET", REPO_ROOT / "data" / "processed" / "facilities.parquet")
).resolve()

# Authority JSONs the website's API serves as static/cached data, built by
# scripts/export_artifacts.py from the redistribution results.
AUTHORITY_DIR = Path(
    os.getenv("AUTHORITY_DIR", REPO_ROOT / "backend" / "app" / "data" / "authority")
).resolve()

# Sample data for the frontend's upload-template demo.
DEMO_DIR = Path(os.getenv("DEMO_DIR", REPO_ROOT / "data" / "demo")).resolve()

# Time-based train/test split for backend/app/ml/train.py, as "YYYY-MM"
# month strings (inclusive on both ends). Chosen to mirror notebook 07's
# chronological split falling in the same range, but as fixed, reproducible
# months rather than a percentage-of-unique-dates cut.
TRAIN_END_MONTH = os.getenv("TRAIN_END_MONTH", "2023-02")
TEST_START_MONTH = os.getenv("TEST_START_MONTH", "2023-03")
TEST_END_MONTH = os.getenv("TEST_END_MONTH", "2023-10")

# --- API / session ---------------------------------------------------
# Sessions are deliberately temporary: in-memory only, no database. A
# backend restart invalidates every session on purpose (see docs/).
SESSION_TTL_MINUTES = int(os.getenv("SESSION_TTL_MINUTES", "60"))
SESSION_MAX_COUNT = int(os.getenv("SESSION_MAX_COUNT", "200"))
SESSION_MAX_CHAT_TURNS = int(os.getenv("SESSION_MAX_CHAT_TURNS", "30"))

# The Vite dev server proxies /api to this backend, so in development the
# browser sees one origin and the session cookie needs no CORS exemption.
# This list only matters if the frontend is ever served from its own origin.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]

# --- chatbot (Groq) --------------------------------------------------
# Key lives in backend/.env and is never sent to the frontend. When it is
# missing, /api/chat returns a labelled "LLM not configured" error rather
# than a fabricated answer.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Verified against this project's key with `client.models.list()` — the
# Llama models are NOT available on it, so don't reintroduce them without
# re-checking. Working chat models, all 131k context:
#   openai/gpt-oss-120b  (default: best answers, ~0.6s, good Arabic)
#   openai/gpt-oss-20b   (faster, slightly looser)
#   qwen/qwen3.8-27b     (fast, no reasoning pass needed)
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# The gpt-oss models reason before answering and will spend the entire
# token budget thinking if left unbounded — with max_tokens=120 they
# returned empty content. "low" keeps the reasoning pass short enough that
# the answer actually fits. Ignored by models that don't reason (qwen).
GROQ_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "low")

# Guardrails from the brief: answers stay short, and the grounding context
# is truncated before it can blow past the model's context window.
CHAT_MAX_TOKENS = int(os.getenv("CHAT_MAX_TOKENS", "500"))
CHAT_CONTEXT_BUDGET_BYTES = int(os.getenv("CHAT_CONTEXT_BUDGET_BYTES", "40000"))
CHAT_HISTORY_TURNS = int(os.getenv("CHAT_HISTORY_TURNS", "6"))

# --- redistribution defaults ----------------------------------------
MIN_TRANSFER_QTY = float(os.getenv("MIN_TRANSFER_QTY", "10"))
_max_distance = os.getenv("MAX_DISTANCE_KM", "").strip()
MAX_DISTANCE_KM = float(_max_distance) if _max_distance else None

if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print(f"RAW_FORMAT: {RAW_FORMAT}")
    for name, path in [
        ("RAW_DATA", RAW_DATA),
        ("PANEL_PARQUET", PANEL_PARQUET),
        ("FACILITIES_PARQUET", FACILITIES_PARQUET),
        ("MODELS_DIR", MODELS_DIR),
        ("REPORTS_DIR", REPORTS_DIR),
        ("NOTEBOOKS_DIR", NOTEBOOKS_DIR),
        ("AUTHORITY_DIR", AUTHORITY_DIR),
        ("DEMO_DIR", DEMO_DIR),
    ]:
        print(f"{name}: {path} (exists={path.exists()})")
