"""Build everything the website reads as static/served data.

1. Verify models/ holds all five training artifacts.
2. Verify reports/metrics.json passes the same thresholds
   app.ml.evaluate gates on (coverage, WAPE) — so a model that failed
   evaluation can't be exported either.
3. Run the live pipeline (predict -> rules -> redistribute) across the whole
   held-out test period, and write the authority JSONs the API serves from
   backend/app/data/authority/:
     - overview.json: top-level KPIs for the period
     - products.json: per-product deficit/surplus/coverage summary
     - transfers_top.json: the 30 largest recommended transfers
     - metrics.json: a copy of reports/metrics.json (the last evaluation)
4. Cut one facility-month out of the panel into data/demo/, in the
   upload-template format (see UPLOAD_TEMPLATE_COLUMNS below), for the
   frontend's "try it with sample data" flow.

Usage (from the repo root):
    python scripts/export_artifacts.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pandas as pd  # noqa: E402

from app.core.config import (  # noqa: E402
    AUTHORITY_DIR,
    DEMO_DIR,
    MODELS_DIR,
    PANEL_PARQUET,
    REPORTS_DIR,
    TEST_END_MONTH,
    TEST_START_MONTH,
)
from app.ml import predict  # noqa: E402
from app.ml.evaluate import COVERAGE_MAX, COVERAGE_MIN, WAPE_MAX  # noqa: E402
from app.ml.redistribute import solve_all  # noqa: E402
from app.ml.rules import apply_rules  # noqa: E402

REQUIRED_MODEL_FILES = [
    "preprocessor.joblib",
    "xgb_p10.joblib",
    "xgb_p50.joblib",
    "xgb_p90.joblib",
    "feature_config.json",
]

# Redistribution runs a full LP per (product, month); real (product, month)
# groups here run up to ~750 donors x ~350 receivers. A distance cap keeps
# the export tractable — see app/ml/redistribute.py's module docstring for
# why the underlying solver is a continuous LP, not a MILP.
EXPORT_MAX_KM = 150

# Keep only the nearest N donors per receiver. Without this the period-wide
# export is a multi-hour job: the largest product-months have ~260k candidate
# pairs each, across 8 months x 36 products. Stage 2 minimises distance, so
# the pruned far donors are ones the optimiser would rarely pick. Single-month
# solves (the warehouse view) leave this off and consider every pair.
EXPORT_MAX_DONORS_PER_RECEIVER = 25

TOP_TRANSFERS_COUNT = 30

DEMO_FACILITY_HF_PK = 780
DEMO_MONTH = "2023-03"

# What a facility would fill in for one month, across its products — the
# operational S2-style fields, not the S1/S3/S5 enrichment columns added
# during integration (see docs/data_profile.md).
UPLOAD_TEMPLATE_COLUMNS = [
    "hf_pk",
    "name1",
    "productID",
    "date",
    "openBalance",
    "received",
    "consumption",
    "closeBalance",
    "stockout",
]


def verify_model_artifacts():
    missing = [name for name in REQUIRED_MODEL_FILES if not (MODELS_DIR / name).exists()]
    if missing:
        print(f"ERROR: missing model artifacts in {MODELS_DIR}: {missing}")
        print("Run: python -m app.ml.train")
        sys.exit(1)
    print(f"Model artifacts OK: all {len(REQUIRED_MODEL_FILES)} present in {MODELS_DIR}")


def verify_metrics_thresholds():
    metrics_path = REPORTS_DIR / "metrics.json"
    if not metrics_path.exists():
        print(f"ERROR: {metrics_path} not found. Run: python -m app.ml.evaluate")
        sys.exit(1)

    with open(metrics_path, encoding="utf-8") as f:
        metrics = json.load(f)

    overall = metrics["overall"]
    coverage = overall["coverage_p10_p90"]
    wape = overall["p50_wape"]

    ok = (COVERAGE_MIN <= coverage <= COVERAGE_MAX) and (wape <= WAPE_MAX)
    if not ok:
        print(
            f"ERROR: last evaluation fails its gates — coverage={coverage:.4f} "
            f"(need [{COVERAGE_MIN}, {COVERAGE_MAX}]), wape={wape:.4f} (need <= {WAPE_MAX}). "
            "Refusing to export a model that shouldn't reach the website."
        )
        sys.exit(1)

    print(f"Metrics gate OK: coverage={coverage * 100:.2f}%, WAPE={wape * 100:.2f}%")
    return metrics


def run_pipeline(panel):
    """Forecast and solve redistribution across the whole held-out test period.

    The authority view is a network picture over months we can actually
    score, not a single speculative future month — so this walks
    TEST_START_MONTH..TEST_END_MONTH, forecasting each from the month before
    it and solving the LP per (product, month).
    """
    months = [
        str(period)
        for period in pd.period_range(TEST_START_MONTH, TEST_END_MONTH, freq="M")
    ]
    print(f"\nPeriod: {months[0]}..{months[-1]} ({len(months)} months)")

    latest_by_month = []
    for month in months:
        source = (pd.Period(month, freq="M") - 1).to_timestamp()
        forecast_df = predict.forecast(panel, month)
        stock = panel.loc[panel["date_parsed"] == source, ["hf_pk", "productID", "closeBalance"]]
        latest_by_month.append(forecast_df.merge(stock, on=["hf_pk", "productID"], how="inner"))

    merged = pd.concat(latest_by_month, ignore_index=True)
    rules_df = apply_rules(merged)

    print(f"\nSolving redistribution over {len(months)} months (max_km={EXPORT_MAX_KM})...")
    transfers, product_summary, month_summary, overall_summary = solve_all(
        rules_df,
        max_km=EXPORT_MAX_KM,
        max_donors_per_receiver=EXPORT_MAX_DONORS_PER_RECEIVER,
    )

    period = f"{months[0]}..{months[-1]}"
    return period, rules_df, transfers, product_summary, month_summary, overall_summary


def build_authority_jsons(panel, period, rules_df, transfers, product_summary, overall_summary, eval_metrics):
    AUTHORITY_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()

    overview = {
        "generated_at": generated_at,
        "period": period,
        "rows_forecast": int(len(rules_df)),
        "status_counts": rules_df["madad_status"].value_counts().to_dict(),
        "redistribution": overall_summary,
        "last_evaluation": eval_metrics["overall"],
    }
    with open(AUTHORITY_DIR / "overview.json", "w", encoding="utf-8") as f:
        json.dump(overview, f, indent=2, default=str)

    product_names = panel[["productID", "name1"]].drop_duplicates("productID")
    products = product_summary.merge(product_names, on="productID", how="left")
    products_records = json.loads(products.to_json(orient="records"))
    with open(AUTHORITY_DIR / "products.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": generated_at, "period": period, "products": products_records}, f, indent=2)

    if transfers.empty:
        top_transfers_records = []
    else:
        top_transfers = transfers.sort_values("transfer_quantity", ascending=False).head(TOP_TRANSFERS_COUNT)
        top_transfers_records = json.loads(top_transfers.to_json(orient="records"))
    with open(AUTHORITY_DIR / "transfers_top.json", "w", encoding="utf-8") as f:
        json.dump(
            {"generated_at": generated_at, "period": period, "transfers": top_transfers_records},
            f,
            indent=2,
        )

    with open(AUTHORITY_DIR / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(eval_metrics, f, indent=2, default=str)

    print(f"\nWrote authority JSONs to {AUTHORITY_DIR}:")
    for name in ("overview.json", "products.json", "transfers_top.json", "metrics.json"):
        path = AUTHORITY_DIR / name
        print(f"  {name} ({path.stat().st_size:,} bytes)")


def export_demo_csv(panel):
    demo = panel[
        (panel["hf_pk"] == DEMO_FACILITY_HF_PK) & (panel["date_parsed"] == pd.Timestamp(DEMO_MONTH))
    ][UPLOAD_TEMPLATE_COLUMNS].sort_values("productID")

    if demo.empty:
        print(
            f"WARNING: no rows found for hf_pk={DEMO_FACILITY_HF_PK}, month={DEMO_MONTH} — "
            "skipping demo CSV export."
        )
        return

    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    demo_path = DEMO_DIR / f"facility_{DEMO_FACILITY_HF_PK}_{DEMO_MONTH}.csv"
    demo.to_csv(demo_path, index=False)
    print(f"\nWrote demo file: {demo_path} ({len(demo)} rows)")


def main():
    verify_model_artifacts()
    eval_metrics = verify_metrics_thresholds()

    panel = pd.read_parquet(PANEL_PARQUET)

    period, rules_df, transfers, product_summary, month_summary, overall_summary = run_pipeline(panel)

    build_authority_jsons(panel, period, rules_df, transfers, product_summary, overall_summary, eval_metrics)

    export_demo_csv(panel)

    print("\nDone.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
