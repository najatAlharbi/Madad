"""Forecast orchestration: one facility-month in, served forecast out.

This is the glue between the HTTP layer and the notebook-derived model
code. It exists so app/api/forecast.py stays a thin transport shell and so
the same path is reusable from tests and scripts.

The whole point of the runtime cache is visible here: we build features for
one facility's rows (~0.4s) against precomputed aggregate tables, instead
of rebuilding the full 457k-row panel (~11s) per request.
"""

from __future__ import annotations

import logging
import time

import numpy as np
import pandas as pd

from app.core.runtime import Runtime
from app.ml.features import build_features
from app.ml.rules import apply_rules

logger = logging.getLogger("madad.pipeline")

# How many months of history the forecast chart draws before the forecast point.
HISTORY_MONTHS = 12

SEVERITY_ORDER = {"critical": 0, "at_risk": 1, "surplus": 2}


def _combine_history(runtime: Runtime, facility_id: int, uploaded: pd.DataFrame | None) -> pd.DataFrame:
    """Facility history from the panel, with the uploaded month layered on top.

    The upload wins on a (productID, month) collision so a corrected
    resubmission replaces the stored row rather than duplicating it.
    """
    history = runtime.facility_history(facility_id)
    if uploaded is None or uploaded.empty:
        return history

    combined = pd.concat([history, uploaded], ignore_index=True)
    combined["date_parsed"] = pd.to_datetime(combined["date_parsed"], errors="coerce")
    return (
        combined.sort_values("date_parsed")
        .drop_duplicates(subset=["hf_pk", "productID", "date_parsed"], keep="last")
        .reset_index(drop=True)
    )


def _history_series(rows: pd.DataFrame, product_id: int, forecast_month: pd.Period) -> list[dict]:
    """The chart's 13-month series for one product.

    Shape matches design/screens.md: [{month, actual, forecast, range}] with
    `actual` null on the forecast row. The forecast row's values are filled
    in by the caller, which is the only place that knows the predictions.
    """
    product_rows = rows.loc[rows["productID"] == product_id]
    by_month = {
        row["date_parsed"].to_period("M"): float(row["consumption"])
        for _, row in product_rows.iterrows()
        if pd.notna(row["date_parsed"])
    }

    months = [forecast_month - offset for offset in range(HISTORY_MONTHS, 0, -1)]
    series = [
        {"month": str(month), "actual": by_month.get(month), "forecast": None, "range": None}
        for month in months
    ]
    series.append({"month": str(forecast_month), "actual": None, "forecast": None, "range": None})
    return series


def run_forecast(
    runtime: Runtime,
    facility_id: int,
    forecast_month: str,
    uploaded: pd.DataFrame | None = None,
    is_demo: bool = False,
) -> dict:
    """Forecast next-month consumption for every product at one facility.

    Args:
        runtime: the process-wide cache (models, panel, aggregates).
        facility_id: hf_pk to forecast.
        forecast_month: the month being forecast, "YYYY-MM". Features come
            from the month before it.
        uploaded: optional user-supplied rows for the source month, already
            normalised to panel column names.
        is_demo: marks the run as sample data so the UI can badge it.

    Returns:
        A JSON-serializable payload: facility, month, per-product forecasts
        with stock/status/gap/history, and the status counts.
    """
    started = time.perf_counter()

    target = pd.Period(forecast_month, freq="M")
    source_month = target - 1
    source_timestamp = source_month.to_timestamp()

    rows = _combine_history(runtime, facility_id, uploaded)
    if rows.empty:
        raise ValueError(f"no history for facility {facility_id}")

    features = build_features(rows, for_inference=True, aggregates=runtime.aggregates)
    current = features.loc[features["date_parsed"] == source_timestamp]
    if current.empty:
        raise ValueError(
            f"no data for facility {facility_id} in {source_month} — "
            f"a forecast for {forecast_month} needs that month's stock record"
        )

    # Predict: clip at zero, then sort row-wise so P10 <= P50 <= P90.
    matrix = runtime.preprocessor.transform(current[runtime.feature_columns])
    predictions = np.column_stack(
        [np.clip(runtime.models[name].predict(matrix), 0, None) for name in ("P10", "P50", "P90")]
    )
    predictions = np.sort(predictions, axis=1)

    # Honest low-confidence signal: consumption_lag_1 is null exactly when
    # there was no real observation one calendar month before this row —
    # true for a facility with no stored history at all, and equally true
    # when the source month sits far past any real data (a "forecast"
    # requested for a date the panel never reached). Either way, most of
    # this row's 141 features fell back to the preprocessor's median/mode
    # rather than reflecting this series, so the prediction is a default,
    # not a real forecast, and callers should not present it as one.
    low_confidence = current["consumption_lag_1"].isna().to_numpy() if "consumption_lag_1" in current.columns else False

    stock_lookup = current.set_index("productID")["closeBalance"].to_dict()
    frame = pd.DataFrame(
        {
            "hf_pk": current["hf_pk"].to_numpy(),
            "productID": current["productID"].to_numpy(),
            "month": forecast_month,
            "P10": predictions[:, 0],
            "P50": predictions[:, 1],
            "P90": predictions[:, 2],
            "closeBalance": current["closeBalance"].to_numpy(),
            "low_confidence": low_confidence,
        }
    )
    scored = apply_rules(frame)

    products = []
    for _, row in scored.iterrows():
        product_id = int(row["productID"])
        series = _history_series(rows, product_id, target)
        # Join the lines: the last actual month also carries the forecast
        # value so the solid and dashed lines meet instead of breaking, and
        # a zero-width range so the P10–P90 band opens as a cone from that
        # month rather than having a single point to span (which draws
        # nothing at all).
        if len(series) >= 2 and series[-2]["actual"] is not None:
            anchor = round(float(series[-2]["actual"]), 1)
            series[-2]["forecast"] = anchor
            series[-2]["range"] = [anchor, anchor]
        series[-1]["forecast"] = round(float(row["P50"]), 1)
        series[-1]["range"] = [round(float(row["P10"]), 1), round(float(row["P90"]), 1)]

        products.append(
            {
                "product_id": product_id,
                "name": runtime.product_names.get(product_id, f"Product {product_id}"),
                "stock": float(row["closeBalance"]),
                "p10": round(float(row["P10"]), 1),
                "p50": round(float(row["P50"]), 1),
                "p90": round(float(row["P90"]), 1),
                "status": row["madad_status"],
                "severity": row["severity"],
                "gap": round(float(row["predicted_deficit_p90"]), 1),
                "surplus": round(float(row["potential_surplus_p90"]), 1),
                "low_confidence": bool(row["low_confidence"]),
                "history": series,
            }
        )

    products.sort(key=lambda p: (SEVERITY_ORDER.get(p["severity"], 9), -p["gap"]))

    # A genuinely new facility isn't in the registry (facility_row -> None),
    # but its own facility_type/district may still be sitting on the
    # uploaded rows (from to_panel_rows) — use those rather than reporting
    # this facility as having no attributes at all.
    facility = runtime.facility_row(facility_id)
    is_new_facility = facility is None
    if is_new_facility:
        own_rows = rows.loc[rows["hf_pk"] == facility_id]
        facility = {
            "district": next((d for d in own_rows.get("district", []) if pd.notna(d)), None),
            "facility_type": next((t for t in own_rows.get("facility_type", []) if pd.notna(t)), None),
        }

    counts = {
        "total": len(products),
        "critical": sum(1 for p in products if p["severity"] == "critical"),
        "at_risk": sum(1 for p in products if p["severity"] == "at_risk"),
        "surplus": sum(1 for p in products if p["severity"] == "surplus"),
        "low_confidence": sum(1 for p in products if p["low_confidence"]),
    }

    elapsed = time.perf_counter() - started
    logger.info(
        "forecast facility=%s month=%s products=%d critical=%d in %.2fs",
        facility_id, forecast_month, counts["total"], counts["critical"], elapsed,
    )

    return {
        "facility": {
            "id": facility_id,
            "district": facility.get("district"),
            "facility_type": facility.get("facility_type"),
            "is_new": is_new_facility,
        },
        "forecast_month": forecast_month,
        "source_month": str(source_month),
        "is_demo": is_demo,
        "counts": counts,
        "products": products,
        "model": {
            "name": "XGBoost quantile (P10/P50/P90)",
            "coverage": runtime.authority.get("metrics", {}).get("overall", {}).get("coverage_p10_p90"),
            "p50_mae": runtime.authority.get("metrics", {}).get("overall", {}).get("p50_mae"),
            "p50_mse": runtime.authority.get("metrics", {}).get("overall", {}).get("p50_mse"),
            "test_rows": runtime.authority.get("metrics", {}).get("overall", {}).get("test_rows"),
        },
        "generated_in_seconds": round(elapsed, 2),
    }
