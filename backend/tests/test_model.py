"""Tests for app.ml.features (inference/training parity) and app.ml.predict
(the served forecast). These are integration tests against the real
PANEL_PARQUET and the artifacts written by app.ml.train — they are skipped
if either is missing, rather than failing collection, since a fresh
checkout needs scripts/prepare_data.py and app.ml.train run first.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.core.config import MODELS_DIR, PANEL_PARQUET, TEST_END_MONTH, TEST_START_MONTH
from app.ml import predict
from app.ml.features import build_features

GOLDEN_PATH = Path(__file__).parent / "data" / "golden_predictions.csv"

REQUIRED_ARTIFACTS = [
    PANEL_PARQUET,
    MODELS_DIR / "preprocessor.joblib",
    MODELS_DIR / "xgb_p10.joblib",
    MODELS_DIR / "xgb_p50.joblib",
    MODELS_DIR / "xgb_p90.joblib",
    MODELS_DIR / "feature_config.json",
]

pytestmark = pytest.mark.skipif(
    not all(p.exists() for p in REQUIRED_ARTIFACTS),
    reason="Requires PANEL_PARQUET and trained model artifacts — run "
    "scripts/prepare_data.py and python -m app.ml.train first.",
)


@pytest.fixture(scope="module")
def panel():
    return pd.read_parquet(PANEL_PARQUET)


@pytest.fixture(scope="module")
def features_train(panel):
    return build_features(panel, for_inference=False)


@pytest.fixture(scope="module")
def features_infer(panel):
    return build_features(panel, for_inference=True)


# --- 1. Parity: for_inference=True and for_inference=False must compute the
# exact same feature values for any row both of them keep. ---


def test_parity_features_equal_between_modes(features_train, features_infer):
    key_cols = ["hf_pk", "productID", "date_parsed"]

    test_start = pd.Period(TEST_START_MONTH, freq="M")
    test_end = pd.Period(TEST_END_MONTH, freq="M")

    def in_test_period(df):
        period = df["date_parsed"].dt.to_period("M")
        return df.loc[(period >= test_start) & (period <= test_end)]

    train_in_test = in_test_period(features_train)
    infer_in_test = in_test_period(features_infer)

    shared_keys = train_in_test[key_cols].merge(infer_in_test[key_cols], on=key_cols, how="inner")
    assert len(shared_keys) >= 200, "not enough shared rows in the test period to sample 200 from"

    sample_keys = shared_keys.sample(n=200, random_state=42)

    merged = sample_keys.merge(train_in_test, on=key_cols).merge(
        infer_in_test, on=key_cols, suffixes=("_train", "_infer")
    )
    assert len(merged) == 200

    feature_cols = [c for c in features_train.columns if c not in key_cols]

    for col in feature_cols:
        train_vals = merged[f"{col}_train"]
        infer_vals = merged[f"{col}_infer"]

        if pd.api.types.is_numeric_dtype(train_vals):
            assert np.allclose(
                train_vals.to_numpy(dtype=float),
                infer_vals.to_numpy(dtype=float),
                atol=1e-9,
                equal_nan=True,
            ), f"mismatch in numeric feature {col!r}"
        else:
            train_str = train_vals.astype("string").fillna("<NA>")
            infer_str = infer_vals.astype("string").fillna("<NA>")
            assert (train_str == infer_str).all(), f"mismatch in categorical feature {col!r}"


# --- 2. The latest month per series has no valid next-month target, so
# for_inference=False drops it, but for_inference=True must keep it. ---


def test_latest_month_survives_only_in_inference_mode(features_train, features_infer):
    infer_last = features_infer.sort_values("date_parsed").groupby(["hf_pk", "productID"]).tail(1)

    train_keys = set(
        map(tuple, features_train[["hf_pk", "productID", "date_parsed"]].itertuples(index=False, name=None))
    )

    candidate = None
    for row in infer_last.itertuples():
        key = (row.hf_pk, row.productID, row.date_parsed)
        if key not in train_keys:
            candidate = key
            break

    assert candidate is not None, "expected at least one series whose latest month has no valid next-month target"
    hf_pk, product_id, date_parsed = candidate

    in_infer = (
        (features_infer["hf_pk"] == hf_pk)
        & (features_infer["productID"] == product_id)
        & (features_infer["date_parsed"] == date_parsed)
    )
    in_train = (
        (features_train["hf_pk"] == hf_pk)
        & (features_train["productID"] == product_id)
        & (features_train["date_parsed"] == date_parsed)
    )

    assert in_infer.any(), "for_inference=True should keep the latest month"
    assert not in_train.any(), "for_inference=False should drop the latest month (no valid target)"


# --- 3. Predictions must never cross and never go negative. ---


def test_predictions_monotonic_and_nonnegative(panel):
    result = predict.forecast(panel, "2023-11")
    sample = result.sample(n=500, random_state=42)

    assert (sample["P10"] <= sample["P50"]).all()
    assert (sample["P50"] <= sample["P90"]).all()
    assert (sample[["P10", "P50", "P90"]] >= 0).all().all()


# --- 4. Golden: predictions for a fixed set of rows must not silently
# drift as the code changes. Regenerate tests/data/golden_predictions.csv
# deliberately (and review the diff) when a change is meant to move
# predictions. ---


def test_golden_predictions_match(panel):
    golden = pd.read_csv(GOLDEN_PATH)
    result = predict.forecast(panel, "2023-11")

    subset = result.merge(golden[["hf_pk", "productID"]], on=["hf_pk", "productID"], how="inner")
    subset = subset.sort_values(["hf_pk", "productID"]).reset_index(drop=True)
    golden_sorted = golden.sort_values(["hf_pk", "productID"]).reset_index(drop=True)

    assert len(subset) == len(golden_sorted) == 20

    for col in ("P10", "P50", "P90"):
        assert np.allclose(
            subset[col].to_numpy(dtype=float), golden_sorted[col].to_numpy(dtype=float), atol=1e-6
        ), f"golden mismatch in {col}"


# --- 5. A schema mismatch must raise a clear, named error — not crash. ---


def test_column_mismatch_raises_clear_error():
    cache = predict.load_models()
    expected = cache["feature_config"]["feature_columns"]

    available = ["date_parsed"] + [c for c in expected if c != "consumption"]

    with pytest.raises(ValueError, match="consumption"):
        predict._validate_feature_columns(available, expected)


# --- 6. A series with almost no history should still get a forecast,
# flagged as low_history, rather than raising. ---


def test_cold_start_returns_low_history_flag(panel):
    template = panel.iloc[[0]].copy()

    row1 = template.copy()
    row1["date_parsed"] = pd.Timestamp("2023-09-01")
    row2 = template.copy()
    row2["date_parsed"] = pd.Timestamp("2023-10-01")

    synthetic = pd.concat([row1, row2], ignore_index=True)

    result = predict.forecast(synthetic, "2023-11")

    assert len(result) == 1
    assert bool(result.loc[0, "low_history"]) is True
    assert result.loc[0, ["P10", "P50", "P90"]].notna().all()
