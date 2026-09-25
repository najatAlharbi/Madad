"""Serve forecasts from the trained P10/P50/P90 quantile models.

load_models() loads the artifacts written by app.ml.train once and caches
them in module state (so a long-running API process pays the load cost a
single time, not once per request). forecast() builds inference-mode
features for a batch of history rows and returns next-month P10/P50/P90
predictions for whichever month directly follows the latest month in that
history.
"""

import json
import time

import joblib
import numpy as np
import pandas as pd
import xgboost

from app.core.config import MODELS_DIR
from app.ml.features import build_features

MODEL_FILES = {"P10": "xgb_p10.joblib", "P50": "xgb_p50.joblib", "P90": "xgb_p90.joblib"}

# Not from the notebook: there is no training-time concept of "too little
# history to trust". This is a serving-time heuristic so a near-empty
# series still gets a forecast (imputation handles the missing lags fine)
# rather than being silently indistinguishable from a well-observed one.
# Set to match the notebook's own bar for its shortest rolling window
# (ROLLING_WINDOWS' (3, 2) in features.py: at least 2 of the last 3 months
# populated) — i.e. flag a row backed by fewer than 2 prior observations.
LOW_HISTORY_MIN_PRIOR_OBSERVATIONS = 2

_CACHE = {}


def _validate_feature_columns(available_columns, expected_columns):
    """expected_columns is feature_config['feature_columns']. available_columns
    is whatever build_features actually produced (its output always includes
    date_parsed, which is not itself a feature, so it is excluded here).
    """
    available_set = set(available_columns) - {"date_parsed"}
    expected_set = set(expected_columns)

    missing = sorted(expected_set - available_set)
    extra = sorted(available_set - expected_set)

    if missing or extra:
        parts = []
        if missing:
            parts.append(f"missing columns: {missing}")
        if extra:
            parts.append(f"unexpected extra columns: {extra}")
        raise ValueError(
            "build_features output does not match models/feature_config.json's "
            "feature_columns — " + "; ".join(parts)
        )


def load_models(force_reload=False):
    """Load preprocessor, the three quantile models, and feature_config.json
    from MODELS_DIR. Cached at module level after the first call.
    """
    if not force_reload and _CACHE:
        return _CACHE

    preprocessor = joblib.load(MODELS_DIR / "preprocessor.joblib")
    models = {name: joblib.load(MODELS_DIR / filename) for name, filename in MODEL_FILES.items()}

    with open(MODELS_DIR / "feature_config.json", encoding="utf-8") as f:
        feature_config = json.load(f)

    # Force CPU prediction regardless of what device the models were
    # trained with — a serving process should not assume a GPU is present.
    for model in models.values():
        model.set_params(device="cpu")

    installed_version = xgboost.__version__
    expected_version = feature_config["versions"]["xgboost"]
    assert installed_version == expected_version, (
        f"Installed xgboost {installed_version} does not match the version "
        f"these models were trained with ({expected_version}). Predictions "
        f"from a mismatched xgboost version are not guaranteed to reproduce "
        f"training-time behaviour — refusing to load."
    )

    _CACHE.clear()
    _CACHE.update(preprocessor=preprocessor, models=models, feature_config=feature_config)
    return _CACHE


def forecast(history_df: pd.DataFrame, target_month) -> pd.DataFrame:
    """Forecast P10/P50/P90 consumption for target_month, for every
    (hf_pk, productID) series in history_df whose most recent observed
    month is exactly the month before target_month.

    Args:
        history_df: monthly facility-product rows, same schema as
            PANEL_PARQUET.
        target_month: the month being forecast, as a "YYYY-MM" string (or
            anything pandas.Period accepts).

    Returns:
        DataFrame with hf_pk, productID, month (= target_month),
        P10, P50, P90, and low_history (True when the row is backed by
        fewer than LOW_HISTORY_MIN_PRIOR_OBSERVATIONS prior months, per the
        module docstring above).
    """
    cache = load_models()
    preprocessor = cache["preprocessor"]
    models = cache["models"]
    feature_columns = cache["feature_config"]["feature_columns"]

    rows_in = len(history_df)

    features_df = build_features(history_df, for_inference=True)
    _validate_feature_columns(features_df.columns, feature_columns)

    source_month_start = (pd.Period(target_month, freq="M") - 1).to_timestamp()
    rows_for_month = features_df.loc[features_df["date_parsed"] == source_month_start].copy()

    if "facility_product_observation_count_prior" in rows_for_month.columns:
        low_history = (
            rows_for_month["facility_product_observation_count_prior"] < LOW_HISTORY_MIN_PRIOR_OBSERVATIONS
        ).to_numpy()
    else:
        low_history = np.zeros(len(rows_for_month), dtype=bool)

    X = rows_for_month[feature_columns]

    start = time.perf_counter()
    X_t = preprocessor.transform(X)
    predictions = np.column_stack([models[name].predict(X_t) for name in ("P10", "P50", "P90")])
    # Sort row-wise to enforce non-crossing quantiles, then clip at zero
    # (clipping is monotonic, so this order and the reverse give the same
    # result — see backend/app/ml/evaluate.py for the equivalent step).
    predictions = np.sort(predictions, axis=1)
    predictions = np.clip(predictions, 0, None)
    elapsed = time.perf_counter() - start

    result = pd.DataFrame(
        {
            "hf_pk": rows_for_month["hf_pk"].to_numpy(),
            "productID": rows_for_month["productID"].to_numpy(),
            "month": str(target_month),
            "P10": predictions[:, 0],
            "P50": predictions[:, 1],
            "P90": predictions[:, 2],
            "low_history": low_history,
        }
    ).reset_index(drop=True)

    print(f"Rows in: {rows_in:,}")
    print(f"Features built: {features_df.shape[0]:,} rows x {features_df.shape[1]:,} columns")
    print(f"Rows forecast for {target_month}: {len(result):,}")
    print(f"Prediction time: {elapsed:.4f}s")

    return result
