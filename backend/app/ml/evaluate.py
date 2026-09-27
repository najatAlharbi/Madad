"""Evaluate the trained P10/P50/P90 quantile models on the held-out test
split (notebook 07, cells 15-16: "ONE-TIME FINAL TEST PREDICTIONS" and
"FINAL TEST METRICS").

Loads the artifacts written by app.ml.train, rebuilds the exact same test
split from PANEL_PARQUET (same feature engineering, same configured test
month range), predicts, and reports coverage, pinball loss, P50 MAE/RMSE
/WAPE/R2, and mean interval width — plus a per-month breakdown and a
per-product breakdown for the ten worst products, and writes all of it to
reports/metrics.json.

Predictions are clipped at zero and then sorted row-wise to enforce
non-crossing quantiles, in that order, exactly as notebook cell 15 does.

Exits non-zero if P10-P90 coverage falls outside [78%, 84%] or P50 WAPE
exceeds 60% — a gate so a model that regressed can't reach the website.

Usage (from backend/, per README.md):
    python -m app.ml.evaluate
"""

import json
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_pinball_loss, mean_squared_error, r2_score

from app.core.config import MODELS_DIR, PANEL_PARQUET, REPORTS_DIR, TEST_END_MONTH, TEST_START_MONTH
from app.ml.features import TARGET_COLUMN, build_features, build_target
from app.ml.train import QUANTILES

COVERAGE_MIN = 0.78
COVERAGE_MAX = 0.84
WAPE_MAX = 0.60

METRICS_PATH = REPORTS_DIR / "metrics.json"

MODEL_FILES = {"P10": "xgb_p10.joblib", "P50": "xgb_p50.joblib", "P90": "xgb_p90.joblib"}


def month_mask(dates, start_month, end_month):
    periods = dates.dt.to_period("M")
    return (periods >= pd.Period(start_month, freq="M")) & (periods <= pd.Period(end_month, freq="M"))


def regression_metrics(y_true, y_pred):
    """Same formulas as notebook cell 9's regression_metrics."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    mae = mean_absolute_error(y_true, y_pred)
    mse = float(mean_squared_error(y_true, y_pred))
    rmse = float(np.sqrt(mse))
    r2 = r2_score(y_true, y_pred)
    denominator = np.sum(np.abs(y_true))
    wape = float(np.sum(np.abs(y_true - y_pred)) / denominator) if denominator > 0 else float("nan")
    return {"MAE": float(mae), "MSE": mse, "RMSE": rmse, "WAPE": wape, "R2": float(r2)}


def load_artifacts():
    preprocessor = joblib.load(MODELS_DIR / "preprocessor.joblib")
    models = {name: joblib.load(MODELS_DIR / filename) for name, filename in MODEL_FILES.items()}
    with open(MODELS_DIR / "feature_config.json", encoding="utf-8") as f:
        feature_config = json.load(f)
    return preprocessor, models, feature_config


def build_test_split():
    panel = pd.read_parquet(PANEL_PARQUET)
    features = build_features(panel, for_inference=False)
    target = build_target(panel)
    data = features.merge(target, on=["hf_pk", "productID", "date_parsed"], how="inner")

    test_mask = month_mask(data["date_parsed"], TEST_START_MONTH, TEST_END_MONTH)
    test_df = data.loc[test_mask].reset_index(drop=True)

    # Product names are not a model feature, but make the per-product
    # breakdown readable.
    if "name1" in panel.columns:
        product_names = panel[["productID", "name1"]].drop_duplicates("productID")
        test_df = test_df.merge(product_names, on="productID", how="left")

    return test_df


def predict_quantiles(preprocessor, models, X):
    X_t = preprocessor.transform(X)

    # Clip at zero, THEN sort row-wise to enforce non-crossing quantiles —
    # same order as notebook cell 15.
    raw = {name: np.clip(model.predict(X_t), 0, None) for name, model in models.items()}
    stacked = np.column_stack([raw["P10"], raw["P50"], raw["P90"]])
    sorted_q = np.sort(stacked, axis=1)
    return sorted_q[:, 0], sorted_q[:, 1], sorted_q[:, 2]


def compute_overall_metrics(y_true, p10, p50, p90):
    p10_pinball = float(mean_pinball_loss(y_true, p10, alpha=QUANTILES["P10"]))
    p50_pinball = float(mean_pinball_loss(y_true, p50, alpha=QUANTILES["P50"]))
    p90_pinball = float(mean_pinball_loss(y_true, p90, alpha=QUANTILES["P90"]))
    p50_metrics = regression_metrics(y_true, p50)
    coverage = float(np.mean((y_true >= p10) & (y_true <= p90)))
    interval_width = float(np.mean(p90 - p10))

    return {
        "test_rows": int(len(y_true)),
        "coverage_p10_p90": coverage,
        "mean_interval_width": interval_width,
        "p10_pinball": p10_pinball,
        "p50_pinball": p50_pinball,
        "p90_pinball": p90_pinball,
        "p50_mae": p50_metrics["MAE"],
        "p50_mse": p50_metrics["MSE"],
        "p50_rmse": p50_metrics["RMSE"],
        "p50_wape": p50_metrics["WAPE"],
        "p50_r2": p50_metrics["R2"],
    }


def print_overall_table(overall):
    rows = [
        ("Test rows", f"{overall['test_rows']:,}"),
        ("P10-P90 coverage", f"{overall['coverage_p10_p90'] * 100:.2f}%"),
        ("Mean interval width", f"{overall['mean_interval_width']:.2f}"),
        ("P10 pinball loss", f"{overall['p10_pinball']:.4f}"),
        ("P50 pinball loss", f"{overall['p50_pinball']:.4f}"),
        ("P90 pinball loss", f"{overall['p90_pinball']:.4f}"),
        ("P50 MAE", f"{overall['p50_mae']:.4f}"),
        ("P50 MSE", f"{overall['p50_mse']:.4f}"),
        ("P50 RMSE", f"{overall['p50_rmse']:.4f}"),
        ("P50 WAPE", f"{overall['p50_wape'] * 100:.2f}%"),
        ("P50 R2", f"{overall['p50_r2']:.4f}"),
    ]
    width = max(len(label) for label, _ in rows)
    print("\n=== Overall test metrics ===")
    for label, value in rows:
        print(f"  {label.ljust(width)} : {value}")


def compute_monthly_breakdown(test_df):
    records = []
    for period, group in test_df.groupby(test_df["date_parsed"].dt.to_period("M")):
        y = group[TARGET_COLUMN].values
        p10, p50, p90 = group["P10"].values, group["P50"].values, group["P90"].values
        metrics = regression_metrics(y, p50)
        records.append(
            {
                "month": str(period),
                "rows": int(len(group)),
                "coverage_p10_p90": float(np.mean((y >= p10) & (y <= p90))),
                "mean_interval_width": float(np.mean(p90 - p10)),
                "p50_mae": metrics["MAE"],
                "p50_mse": metrics["MSE"],
                "p50_wape": metrics["WAPE"],
                "p50_r2": metrics["R2"],
            }
        )
    return records


def compute_top_products(test_df, top_n=10):
    group_cols = ["productID"] + (["name1"] if "name1" in test_df.columns else [])
    stats = (
        test_df.groupby(group_cols)
        .agg(
            rows=("Absolute_Error_P50", "size"),
            total_abs_error_p50=("Absolute_Error_P50", "sum"),
            mean_abs_error_p50=("Absolute_Error_P50", "mean"),
        )
        .reset_index()
        .sort_values("total_abs_error_p50", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )
    return stats


def main():
    preprocessor, models, feature_config = load_artifacts()
    feature_columns = feature_config["feature_columns"]

    test_df = build_test_split()
    print(f"Test rows: {len(test_df):,} ({TEST_START_MONTH}..{TEST_END_MONTH})")

    X_test = test_df[feature_columns]
    y_test = test_df[TARGET_COLUMN].values

    p10, p50, p90 = predict_quantiles(preprocessor, models, X_test)
    test_df = test_df.assign(P10=p10, P50=p50, P90=p90)
    test_df["Absolute_Error_P50"] = np.abs(test_df[TARGET_COLUMN] - test_df["P50"])

    overall = compute_overall_metrics(y_test, p10, p50, p90)
    print_overall_table(overall)

    monthly = compute_monthly_breakdown(test_df)
    monthly_df = pd.DataFrame(monthly)
    print("\n=== Per-month breakdown ===")
    print(monthly_df.to_string(index=False))

    top_products = compute_top_products(test_df, top_n=10)
    print("\n=== Top 10 products by total P50 absolute error ===")
    print(top_products.to_string(index=False))

    report = {
        "overall": overall,
        "per_month": monthly,
        "top_10_products_by_error": top_products.to_dict(orient="records"),
        "gates": {"coverage_min": COVERAGE_MIN, "coverage_max": COVERAGE_MAX, "wape_max": WAPE_MAX},
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nWrote {METRICS_PATH}")

    failed = False
    coverage = overall["coverage_p10_p90"]
    wape = overall["p50_wape"]

    if not (COVERAGE_MIN <= coverage <= COVERAGE_MAX):
        print(f"\nFAIL: P10-P90 coverage {coverage * 100:.2f}% outside [{COVERAGE_MIN * 100:.0f}%, {COVERAGE_MAX * 100:.0f}%]")
        failed = True

    if wape > WAPE_MAX:
        print(f"\nFAIL: P50 WAPE {wape * 100:.2f}% above {WAPE_MAX * 100:.0f}%")
        failed = True

    if failed:
        sys.exit(1)

    print("\nAll gates passed.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
