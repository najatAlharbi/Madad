"""Train the locked P10/P50/P90 XGBoost quantile models (notebook 07,
cells 9-14 and cell 18's save step), on top of ``build_features``.

Usage (from backend/, per README.md):
    python -m app.ml.train
    python -m app.ml.train --sample 50   # fast smoke run on 50 series

Deviation from the notebook, flagged rather than silently applied: cell 14
hardcodes ``device='cuda'``, which fails outright on a machine without a
CUDA GPU. This script probes for a working CUDA device once and falls back
to ``device='cpu'`` if none is found, printing which one it used. Nothing
about the model configuration itself changes — only which device runs it.
"""

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBRegressor

from app.core.config import MODELS_DIR, PANEL_PARQUET, TEST_END_MONTH, TEST_START_MONTH, TRAIN_END_MONTH
from app.ml.features import CATEGORICAL_FEATURES, TARGET_COLUMN, build_features, build_target

RANDOM_STATE = 42
QUANTILES = {"P10": 0.10, "P50": 0.50, "P90": 0.90}

# Notebook cell 13's "LOCKED FINAL CONFIGURATIONS" — the only place these
# values are typed. Every other use loads them back from
# models/locked_final_configs.json (written once, below).
LOCKED_CONFIGS = {
    "P10": {
        "n_estimators": 600,
        "max_depth": 5,
        "learning_rate": 0.03,
        "min_child_weight": 5,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "reg_alpha": 0.10,
        "reg_lambda": 2.0,
    },
    "P50": {
        "n_estimators": 1200,
        "max_depth": 6,
        "learning_rate": 0.03,
        "min_child_weight": 5,
        "subsample": 0.90,
        "colsample_bytree": 0.90,
        "reg_alpha": 0.10,
        "reg_lambda": 2.0,
    },
    "P90": {
        "n_estimators": 1194,
        "max_depth": 6,
        "learning_rate": 0.05,
        "min_child_weight": 10,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "reg_alpha": 0.20,
        "reg_lambda": 3.0,
    },
}

LOCKED_CONFIGS_PATH = MODELS_DIR / "locked_final_configs.json"


def load_locked_configs():
    """Write LOCKED_CONFIGS to disk once if it isn't there yet, then always
    read the on-disk copy back — so retraining always trains from the file,
    not from whatever happens to be typed in this module.
    """
    if not LOCKED_CONFIGS_PATH.exists():
        LOCKED_CONFIGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOCKED_CONFIGS_PATH, "w", encoding="utf-8") as f:
            json.dump(LOCKED_CONFIGS, f, indent=2)
        print(f"Wrote locked configs to {LOCKED_CONFIGS_PATH}")

    with open(LOCKED_CONFIGS_PATH, encoding="utf-8") as f:
        return json.load(f)


def detect_device():
    """Notebook cell 14 hardcodes device='cuda'. Probe once instead of
    assuming a GPU is present; fall back to CPU if it isn't.

    xgboost does NOT raise when 'cuda' is requested but no GPU exists — it
    silently falls back to CPU and only emits a UserWarning ("No visible
    GPU is found, setting device to CPU"). A bare try/except around the
    probe fit would therefore never catch the no-GPU case and would
    misreport "cuda" while actually training on CPU. Watching for that
    warning is what actually distinguishes the two cases.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            probe = XGBRegressor(tree_method="hist", device="cuda", n_estimators=1)
            probe.fit(np.zeros((2, 1)), np.zeros(2))
        except Exception:
            return "cpu"

    gpu_missing = any("No visible GPU" in str(w.message) for w in caught)
    return "cpu" if gpu_missing else "cuda"


def build_preprocessor(numeric_features, categorical_features):
    numeric_pipeline = Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))])
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=True)),
        ]
    )
    return ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, numeric_features),
            ("cat", categorical_pipeline, categorical_features),
        ],
        remainder="drop",
    )


def month_mask(dates, start_month=None, end_month=None):
    periods = dates.dt.to_period("M")
    mask = pd.Series(True, index=dates.index)
    if start_month is not None:
        mask &= periods >= pd.Period(start_month, freq="M")
    if end_month is not None:
        mask &= periods <= pd.Period(end_month, freq="M")
    return mask


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Train on only the first N (hf_pk, productID) series, for a fast smoke run.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    panel = pd.read_parquet(PANEL_PARQUET)
    print(f"Rows loaded: {len(panel):,}")

    if args.sample:
        sample_keys = panel[["hf_pk", "productID"]].drop_duplicates().head(args.sample)
        panel = panel.merge(sample_keys, on=["hf_pk", "productID"], how="inner")
        print(f"--sample {args.sample}: reduced to {panel['hf_pk'].astype(str).str.cat(panel['productID'].astype(str), sep='-').nunique():,} series, {len(panel):,} rows")

    features = build_features(panel, for_inference=False)
    target = build_target(panel)
    data = features.merge(target, on=["hf_pk", "productID", "date_parsed"], how="inner")
    assert len(data) == len(features), "build_features and build_target disagreed on which rows have a valid target"
    print(f"Features built: {features.shape[0]:,} rows x {features.shape[1]:,} columns")

    categorical_features = [c for c in CATEGORICAL_FEATURES if c in data.columns]
    numeric_features = [
        c for c in data.columns if c not in categorical_features and c not in ("date_parsed", TARGET_COLUMN)
    ]

    train_mask = month_mask(data["date_parsed"], end_month=TRAIN_END_MONTH)
    test_mask = month_mask(data["date_parsed"], start_month=TEST_START_MONTH, end_month=TEST_END_MONTH)

    train_df = data.loc[train_mask].reset_index(drop=True)
    test_df = data.loc[test_mask].reset_index(drop=True)

    print(f"Train rows: {len(train_df):,} (<= {TRAIN_END_MONTH})")
    print(f"Test rows: {len(test_df):,} ({TEST_START_MONTH}..{TEST_END_MONTH})")

    feature_cols = numeric_features + categorical_features
    X_train = train_df[feature_cols]
    y_train = train_df[TARGET_COLUMN].values
    X_test = test_df[feature_cols]

    preprocessor = build_preprocessor(numeric_features, categorical_features)
    X_train_t = preprocessor.fit_transform(X_train)
    preprocessor.transform(X_test)  # fit on train only; just confirm test transforms cleanly

    locked_configs = load_locked_configs()
    device = detect_device()
    print(f"XGBoost device: {device}")

    common_params = {
        "objective": "reg:quantileerror",
        "random_state": RANDOM_STATE,
        "tree_method": "hist",
        "device": device,
        "n_jobs": -1,
    }

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    models = {}
    training_times = {}
    for name, alpha in QUANTILES.items():
        config = locked_configs[name]
        model = XGBRegressor(quantile_alpha=alpha, **common_params, **config)

        start = time.perf_counter()
        model.fit(X_train_t, y_train, verbose=False)
        elapsed = time.perf_counter() - start

        training_times[name] = elapsed
        models[name] = model
        print(f"Trained {name} (alpha={alpha}) in {elapsed:.1f}s")

    artifact_paths = {
        "preprocessor": MODELS_DIR / "preprocessor.joblib",
        "xgb_p10": MODELS_DIR / "xgb_p10.joblib",
        "xgb_p50": MODELS_DIR / "xgb_p50.joblib",
        "xgb_p90": MODELS_DIR / "xgb_p90.joblib",
    }

    joblib.dump(preprocessor, artifact_paths["preprocessor"])
    joblib.dump(models["P10"], artifact_paths["xgb_p10"])
    joblib.dump(models["P50"], artifact_paths["xgb_p50"])
    joblib.dump(models["P90"], artifact_paths["xgb_p90"])

    feature_config = {
        "feature_columns": list(preprocessor.feature_names_in_),
        "target": TARGET_COLUMN,
        "train_month_range": {
            "configured_end": TRAIN_END_MONTH,
            "actual_start": str(train_df["date_parsed"].min().to_period("M")),
            "actual_end": str(train_df["date_parsed"].max().to_period("M")),
        },
        "test_month_range": {
            "configured_start": TEST_START_MONTH,
            "configured_end": TEST_END_MONTH,
            "actual_start": str(test_df["date_parsed"].min().to_period("M")) if len(test_df) else None,
            "actual_end": str(test_df["date_parsed"].max().to_period("M")) if len(test_df) else None,
        },
        "hyperparameters": {
            "common": common_params,
            "quantiles": QUANTILES,
            **{name: locked_configs[name] for name in QUANTILES},
        },
        "versions": {
            "xgboost": xgboost.__version__,
            "scikit-learn": sklearn.__version__,
        },
    }

    feature_config_path = MODELS_DIR / "feature_config.json"
    with open(feature_config_path, "w", encoding="utf-8") as f:
        json.dump(feature_config, f, indent=2)
    artifact_paths["feature_config"] = feature_config_path

    print("\nArtifacts written:")
    for name, path in artifact_paths.items():
        print(f"  {name}: {path}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
