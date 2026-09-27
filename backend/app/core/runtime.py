"""Process-wide read-only state, loaded once at startup.

This is the answer to "train once, not per inference". Nothing here is
per-user and nothing here is ever retrained at request time:

- the three quantile models + preprocessor are deserialized once,
- the historical panel is read from parquet once,
- the lagged product / district-product aggregate tables — the expensive
  part of feature building, because they read every facility's rows — are
  computed once and reused by every forecast,
- the facility registry, product names and precomputed authority JSONs
  are read once.

A forecast request therefore only builds features for the rows of the one
facility it concerns (~0.4s) instead of the whole panel (~11s), and the
feature values are byte-identical either way (verified in
tests/test_runtime.py).

Retraining is an explicit offline step: `python -m app.ml.train`. Restart
the API to pick up new artifacts.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

import pandas as pd

from app.core.config import AUTHORITY_DIR, FACILITIES_PARQUET, PANEL_PARQUET
from app.ml import predict
from app.ml.features import build_aggregates

logger = logging.getLogger("madad.runtime")

AUTHORITY_FILES = ("overview", "products", "transfers_top", "metrics")


@dataclass
class Runtime:
    """Everything the API needs in memory. Treat as read-only."""

    preprocessor: object
    models: dict
    feature_config: dict
    panel: pd.DataFrame
    facilities: pd.DataFrame
    aggregates: dict
    product_names: dict[int, str]
    authority: dict[str, dict]
    loaded_at: float = field(default_factory=time.time)

    @property
    def feature_columns(self) -> list[str]:
        return self.feature_config["feature_columns"]

    @property
    def latest_panel_month(self) -> pd.Period:
        """Last month present in the historical panel."""
        return self.panel["date_parsed"].max().to_period("M")

    @property
    def default_forecast_month(self) -> str:
        """The month we forecast by default: the one after the panel ends."""
        return str(self.latest_panel_month + 1)

    def facility_row(self, facility_id: int) -> dict | None:
        """Registry lookup: facility_type, district, latitude, longitude."""
        match = self.facilities.loc[self.facilities["hf_pk"] == facility_id]
        return None if match.empty else match.iloc[0].to_dict()

    def facility_history(self, facility_id: int) -> pd.DataFrame:
        """Every historical row for one facility, all products."""
        return self.panel.loc[self.panel["hf_pk"] == facility_id].copy()

    def known_product_ids(self) -> set[int]:
        return set(self.product_names)


_RUNTIME: Runtime | None = None


def load_runtime(force: bool = False) -> Runtime:
    """Load models, panel, aggregates and authority data into memory.

    Called once from the FastAPI lifespan handler. Raises if the panel or
    the model artifacts are missing, because an API that cannot forecast is
    not usefully "up" — /api/health reports the same thing without raising.
    """
    global _RUNTIME
    if _RUNTIME is not None and not force:
        return _RUNTIME

    started = time.perf_counter()

    if not PANEL_PARQUET.exists():
        raise FileNotFoundError(f"{PANEL_PARQUET} missing — run `python scripts/prepare_data.py` first")

    cache = predict.load_models(force_reload=force)
    logger.info("models loaded (xgboost %s)", cache["feature_config"]["versions"]["xgboost"])

    panel = pd.read_parquet(PANEL_PARQUET)
    panel["date_parsed"] = pd.to_datetime(panel["date_parsed"], errors="coerce")
    logger.info("panel loaded: %s rows, through %s", f"{len(panel):,}", panel["date_parsed"].max().date())

    facilities = (
        pd.read_parquet(FACILITIES_PARQUET)
        if FACILITIES_PARQUET.exists()
        else panel[["hf_pk", "facility_type", "district"]].drop_duplicates("hf_pk").assign(latitude=None, longitude=None)
    )

    aggregates = build_aggregates(panel)
    logger.info("aggregate tables precomputed: %s", ", ".join(sorted(aggregates)))

    product_names = (
        panel[["productID", "name1"]]
        .drop_duplicates("productID")
        .set_index("productID")["name1"]
        .to_dict()
    )

    authority: dict[str, dict] = {}
    for name in AUTHORITY_FILES:
        path = AUTHORITY_DIR / f"{name}.json"
        if path.exists():
            with open(path, encoding="utf-8") as handle:
                authority[name] = json.load(handle)
        else:
            logger.warning("authority file missing: %s — run scripts/export_artifacts.py", path)

    _RUNTIME = Runtime(
        preprocessor=cache["preprocessor"],
        models=cache["models"],
        feature_config=cache["feature_config"],
        panel=panel,
        facilities=facilities,
        aggregates=aggregates,
        product_names=product_names,
        authority=authority,
    )

    logger.info(
        "runtime ready in %.1fs — %d facilities, %d products, authority files: %d",
        time.perf_counter() - started,
        facilities["hf_pk"].nunique(),
        len(product_names),
        len(authority),
    )
    return _RUNTIME


def get_runtime() -> Runtime:
    """Return the loaded runtime, loading it on first use.

    Endpoints depend on this rather than on module globals so a test can
    call load_runtime() itself and get the same object.
    """
    return load_runtime()
