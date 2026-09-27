"""Health/readiness report for the trained model artifacts.

get_health() is what the API exposes at /api/health: which artifacts are
loaded, their size and modified date, the feature count, the trained
month range, the metrics from the last app.ml.evaluate run, library
versions, and process uptime.

Usage (from backend/, per README.md):
    python -m app.ml.health
"""

import importlib.metadata as importlib_metadata
import json
import time
from datetime import datetime, timezone

from app.core.config import GROQ_API_KEY, GROQ_MODEL, MODELS_DIR, REPORTS_DIR

# Set at import time, which for the API is process start.
_STARTED_AT = time.monotonic()

VERSIONED_PACKAGES = ["xgboost", "scikit-learn", "pandas", "numpy", "pulp", "fastapi", "groq"]

ARTIFACT_FILES = [
    "preprocessor.joblib",
    "xgb_p10.joblib",
    "xgb_p50.joblib",
    "xgb_p90.joblib",
    "feature_config.json",
]


def _describe_file(path):
    if not path.exists():
        return {"exists": False}
    stat = path.stat()
    return {
        "exists": True,
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def get_health() -> dict:
    """Everything /api/health needs, as a JSON-serializable dict."""
    artifacts = {name: _describe_file(MODELS_DIR / name) for name in ARTIFACT_FILES}
    all_present = all(info["exists"] for info in artifacts.values())

    feature_count = None
    train_month_range = None
    feature_config_path = MODELS_DIR / "feature_config.json"
    if feature_config_path.exists():
        with open(feature_config_path, encoding="utf-8") as f:
            feature_config = json.load(f)
        feature_count = len(feature_config.get("feature_columns", []))
        train_month_range = feature_config.get("train_month_range")

    last_evaluation_metrics = None
    metrics_path = REPORTS_DIR / "metrics.json"
    if metrics_path.exists():
        with open(metrics_path, encoding="utf-8") as f:
            last_evaluation_metrics = json.load(f).get("overall")

    versions = {}
    for package in VERSIONED_PACKAGES:
        try:
            versions[package] = importlib_metadata.version(package)
        except importlib_metadata.PackageNotFoundError:
            versions[package] = None

    return {
        "status": "ok" if all_present else "degraded",
        "artifacts": artifacts,
        "feature_count": feature_count,
        "train_month_range": train_month_range,
        "last_evaluation_metrics": last_evaluation_metrics,
        "versions": versions,
        "uptime_seconds": round(time.monotonic() - _STARTED_AT, 1),
        # Reports whether the chatbot can run at all, without ever
        # revealing the key itself.
        "chat": {"provider": "groq", "model": GROQ_MODEL, "configured": bool(GROQ_API_KEY)},
    }


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(get_health(), indent=2, default=str))
