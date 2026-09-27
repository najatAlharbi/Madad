"""Feature engineering for the Madad monthly consumption forecast.

This module is a line-for-line port of the feature engineering performed in
``Madad_Models_Notebooks/07_Madad_Final_XGBoost_Test_.ipynb`` (cells 2-7 and
the ``feature_cols`` selection in cell 11). No formula was changed while
moving it — see the module-level NOTE below for the one deliberate behavior
difference (the notebook's data-dependent "drop all-null feature" step is
not reproduced here) and the "things that looked odd" list in the docstring
of :func:`build_features`.

Feature families, and the notebook section each one reproduces:

- **Calendar-safe lags** (notebook cell 4, ``add_calendar_safe_lags``):
  lags 1-12 of ``consumption``, ``received``, ``openBalance``,
  ``closeBalance``, ``stockout`` for each ``(hf_pk, productID)`` series.
  A lag is only filled in when the previous row is *exactly* that many
  calendar months earlier (via ``calendar_month_gap``) — a missing month in
  the series produces a null lag rather than silently pulling in a value
  from further back.
- **Rolling means/stds and history counts** (notebook cell 4): for
  ``consumption``, ``received``, ``closeBalance``, over windows of 3/6/12
  months, computed from the calendar-safe lag columns above, and only
  populated once a minimum number of those lags are non-null (2/3/6
  respectively). Also ``stockout_rate_past_{3,6,12}`` (mean of the
  stockout lags under the same minimum-history rule).
- **Calendar features** (notebook cell 4): ``year``, ``month``,
  ``quarter_num``, and the cyclical ``month_sin`` / ``month_cos`` terms.
- **Derived ratios** (notebook cell 4): ``demand_trend_3_vs_6``,
  ``demand_trend_3_vs_12``, ``current_consumption_vs_12m``,
  ``inventory_runway_3m``, ``received_to_consumption``, and
  ``facility_product_observation_count_prior`` (a leakage-safe count of
  prior observations in the series, via ``cumcount()`` on data already
  sorted by date within each group).
- **Product-level and district-product aggregates** (notebook cell 5,
  ``add_calendar_lagged_aggregate_features``): mean consumption lagged
  1-6 calendar months at the product level and the (district, product)
  level, plus 3/6-month rolling means of those lags and their
  3-vs-6 trend. These are computed from *other rows'* months (the
  aggregate for a given month never includes that month's own row) and
  merged back on an explicit calendar-month offset, so they can only see
  months strictly before the current row's month.
- **Demand-dynamics features** ("Experiment 2", notebook cell 6):
  ``consumption_growth_1m``, ``consumption_growth_rate_1m``,
  ``recent_vs_6m_ratio``, ``recent_vs_12m_ratio``,
  ``consumption_cv_{3,6,12}m``, ``zero_consumption_rate_{3,6,12}m``,
  ``demand_spike_ratio``, ``consumption_momentum_3m``.
- **Raw carried-through numeric features**: ``consumption``, ``received``,
  ``openBalance``, ``closeBalance``, ``normAvg``, ``normStd`` — used
  directly as model inputs in notebook cell 11.
- **Categorical features** (notebook cell 11): ``hf_pk``, ``productID``,
  ``facility_type``, ``district``.

NOTE on the one thing NOT reproduced: notebook cell 11 also drops any
numeric feature that is entirely null *within that notebook run's
Train+Validation split* (``if not trainval_df[c].isna().all()``). That
check is data/split-dependent, not a fixed feature definition, and
reproducing it here would make this function's output columns vary
between calls depending on what happens to be null in a given batch —
which breaks a fixed schema for training vs. inference. This module
always emits the full, fixed feature set instead. Flagged per your
instruction rather than silently "fixed".
"""

import sys
import warnings

import numpy as np
import pandas as pd

GROUP_COLS = ["hf_pk", "productID"]
DATE_COL = "date_parsed"
EPS = 1e-6

KEY_COLUMNS = ["hf_pk", "productID", "date_parsed"]
TARGET_COLUMN = "target_consumption_next_month"

# Raw columns carried straight through as numeric features (notebook cell 11).
RAW_NUMERIC_FEATURES = [
    "consumption",
    "received",
    "openBalance",
    "closeBalance",
    "normAvg",
    "normStd",
]

CALENDAR_FEATURES = ["year", "month", "quarter_num", "month_sin", "month_cos"]

DERIVED_RATIO_FEATURES = [
    "demand_trend_3_vs_6",
    "demand_trend_3_vs_12",
    "current_consumption_vs_12m",
    "inventory_runway_3m",
    "received_to_consumption",
    "facility_product_observation_count_prior",
]

DEMAND_DYNAMICS_FEATURES = [
    "consumption_growth_1m",
    "consumption_growth_rate_1m",
    "recent_vs_6m_ratio",
    "recent_vs_12m_ratio",
    "consumption_cv_3m",
    "consumption_cv_6m",
    "consumption_cv_12m",
    "zero_consumption_rate_3m",
    "zero_consumption_rate_6m",
    "zero_consumption_rate_12m",
    "demand_spike_ratio",
    "consumption_momentum_3m",
]

CATEGORICAL_FEATURES = ["hf_pk", "productID", "facility_type", "district"]

LAG_SOURCE_COLS = ["consumption", "received", "openBalance", "closeBalance", "stockout"]
ROLLING_SOURCE_COLS = ["consumption", "received", "closeBalance"]
ROLLING_WINDOWS = [(3, 2), (6, 3), (12, 6)]
AGGREGATE_PREFIXES = ["product_mean_consumption", "district_product_mean_consumption"]


def _calendar_month_gap(current_date, previous_date):
    return (current_date.dt.year - previous_date.dt.year) * 12 + (
        current_date.dt.month - previous_date.dt.month
    )


def _add_calendar_safe_lags(data, group_cols, date_col, value_cols, lags):
    data = data.copy()
    for col in value_cols:
        if col not in data.columns:
            continue
        grouped = data.groupby(group_cols, sort=False)
        for lag in lags:
            previous_value = grouped[col].shift(lag)
            previous_date = grouped[date_col].shift(lag)
            gap = _calendar_month_gap(data[date_col], previous_date)
            data[f"{col}_lag_{lag}"] = previous_value.where(gap == lag)
    return data


def monthly_aggregate_table(panel, group_keys, source_col="consumption", agg="mean"):
    """The per-month group aggregate that the lagged context features are
    built from (notebook cell 5's inner ``monthly`` frame).

    Split out so a long-running API process can compute it **once** over the
    whole panel at startup and hand it to every later build_features call.
    It depends only on the historical panel, never on which rows are being
    forecast, so caching it changes no feature value — see build_aggregates.
    """
    return (
        panel.groupby(group_keys + [DATE_COL], as_index=False)[source_col]
        .agg(agg)
        .rename(columns={source_col: "_aggregate_value"})
    )


def build_aggregates(panel: pd.DataFrame) -> dict:
    """Precompute both lagged-aggregate lookup tables for a panel.

    Returns a dict suitable for ``build_features(..., aggregates=...)``.
    Computing these is the expensive part of feature building, because they
    read *every* facility's rows; a per-facility request only needs its own
    rows plus these tables.
    """
    df = panel.copy()
    df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce")
    aggregates = {"product_mean_consumption": monthly_aggregate_table(df, ["productID"])}
    if "district" in df.columns:
        aggregates["district_product_mean_consumption"] = monthly_aggregate_table(
            df, ["district", "productID"]
        )
    return aggregates


def _add_calendar_lagged_aggregate_features(
    base_df, group_keys, source_col, prefix, lags, agg, monthly=None
):
    if monthly is None:
        monthly = monthly_aggregate_table(base_df, group_keys, source_col, agg)

    result = base_df
    for lag in lags:
        lagged = monthly.copy()
        lagged[DATE_COL] = lagged[DATE_COL] + pd.offsets.MonthBegin(lag)
        lagged = lagged.rename(columns={"_aggregate_value": f"{prefix}_lag_{lag}"})
        result = result.merge(
            lagged[group_keys + [DATE_COL, f"{prefix}_lag_{lag}"]],
            on=group_keys + [DATE_COL],
            how="left",
        )
    return result


def _safe_ratio(num, den):
    return num / (np.abs(den) + EPS)


def _clean_panel(panel):
    """Notebook cell 2: parse dates, drop rows that can't be grouped or
    lagged at all, sort chronologically within each series. Shared by
    build_features and build_target so both apply the exact same rule.
    """
    df = panel.copy()
    df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce")
    df = df.dropna(subset=[DATE_COL, "hf_pk", "productID", "consumption"]).copy()
    df = df.sort_values(GROUP_COLS + [DATE_COL]).reset_index(drop=True)
    return df


def _compute_target(df):
    """Notebook cell 7: next-calendar-month consumption target. Returns the
    raw target array plus the month_start/next_month_start series used to
    validate the calendar-month gap, so callers can reuse either.
    """
    grouped = df.groupby(GROUP_COLS, sort=False)
    next_date = grouped[DATE_COL].shift(-1)
    next_month_consumption_observed = grouped["consumption"].shift(-1)
    month_start = df[DATE_COL].dt.to_period("M").dt.to_timestamp()
    next_month_start = next_date.dt.to_period("M").dt.to_timestamp()
    expected_next_month = month_start + pd.offsets.MonthBegin(1)
    is_true_next_month = next_month_start == expected_next_month
    target = np.where(is_true_next_month, next_month_consumption_observed, np.nan)
    return target, month_start, next_month_start


def _dynamic_lag_roll_columns(present_columns):
    """Every lag/rolling/history/aggregate column build_features can produce,
    filtered to the ones actually present. Mirrors the notebook's
    ``dynamic_features`` prefix scan (cell 11), but built as an explicit
    list since we know exactly which columns this module creates.
    """
    names = []

    for col in LAG_SOURCE_COLS:
        names += [f"{col}_lag_{lag}" for lag in range(1, 13)]

    for col in ROLLING_SOURCE_COLS:
        for window, _ in ROLLING_WINDOWS:
            names += [f"{col}_history_count_{window}", f"{col}_roll_mean_{window}", f"{col}_roll_std_{window}"]

    for window, _ in ROLLING_WINDOWS:
        names.append(f"stockout_rate_past_{window}")

    for prefix in AGGREGATE_PREFIXES:
        names += [f"{prefix}_lag_{lag}" for lag in range(1, 7)]
        names += [f"{prefix}_roll3", f"{prefix}_roll6", f"{prefix}_trend_3_vs_6"]

    return [c for c in names if c in present_columns]


def build_features(
    panel: pd.DataFrame, for_inference: bool = False, aggregates: dict | None = None
) -> pd.DataFrame:
    """Build the notebook 07 feature set from a monthly facility-product panel.

    Args:
        panel: monthly facility-product rows with (at least) the columns
            ``hf_pk``, ``productID``, ``date_parsed``, ``consumption``,
            ``received``, ``openBalance``, ``closeBalance``, ``stockout``,
            ``normAvg``, ``normStd``, ``facility_type``, ``district`` —
            the schema produced by the integrated CSV (see
            ``docs/data_profile.md``).
        for_inference: if False (training), rows whose next-calendar-month
            target is missing are dropped, exactly as notebook cell 7 does.
            If True, every row is kept, including the most recent month per
            series — the month the notebook always drops because it has no
            observed next month yet, but which is precisely the month we
            need features for at forecast time. The target column is never
            computed into the returned frame either way, so inference never
            depends on it being present.

    Returns:
        A DataFrame with the key columns ``hf_pk``, ``productID``,
        ``date_parsed`` plus every feature from notebook cell 11's
        ``feature_cols`` (all numeric families below, plus the categorical
        features ``hf_pk``, ``productID``, ``facility_type``, ``district``).

    Things worth a second look (not changed, per instructions):
        - ``openBalance`` gets calendar-safe lags but, unlike
          ``consumption``/``received``/``closeBalance``, no rolling
          mean/std/history-count — this matches the notebook exactly
          (cell 4's rolling loop only iterates over the other three), it
          is just an asymmetry in the original feature list, not a bug
          introduced here.
        - ``add_calendar_lagged_aggregate_features`` merges lagged monthly
          aggregates back by adding whole months to ``date_parsed`` and
          joining on equality. This silently assumes every ``date_parsed``
          value is already normalized to the 1st of its month (true for
          this dataset, per docs/data_profile.md) — if that ever stops
          holding, the merge would silently stop matching instead of
          erroring.
        - The notebook's cell 11 additionally drops any numeric feature
          that is 100% null within its own Train+Validation split. This
          function does not reproduce that (see module docstring) because
          it is split-dependent, not a fixed feature definition.
    """
    # This function inserts columns one at a time (mirroring the notebook's
    # own cell-by-cell structure); pandas' fragmentation warning is a
    # performance note, not a correctness issue, so it is silenced here.
    warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)

    df = _clean_panel(panel)

    # --- Calendar-safe lags (cell 4) ---
    lag_source_cols = [c for c in LAG_SOURCE_COLS if c in df.columns]
    df = _add_calendar_safe_lags(df, GROUP_COLS, DATE_COL, lag_source_cols, range(1, 13))

    # --- Rolling means/stds and history counts (cell 4) ---
    for col in ROLLING_SOURCE_COLS:
        if col not in df.columns:
            continue
        for window, min_history in ROLLING_WINDOWS:
            lag_cols = [f"{col}_lag_{lag}" for lag in range(1, window + 1) if f"{col}_lag_{lag}" in df.columns]
            history_count = df[lag_cols].notna().sum(axis=1)
            df[f"{col}_history_count_{window}"] = history_count
            df[f"{col}_roll_mean_{window}"] = df[lag_cols].mean(axis=1, skipna=True).where(history_count >= min_history)
            df[f"{col}_roll_std_{window}"] = df[lag_cols].std(axis=1, skipna=True).where(history_count >= min_history)

    for window, min_history in ROLLING_WINDOWS:
        lag_cols = [f"stockout_lag_{lag}" for lag in range(1, window + 1) if f"stockout_lag_{lag}" in df.columns]
        history_count = df[lag_cols].notna().sum(axis=1)
        df[f"stockout_rate_past_{window}"] = df[lag_cols].mean(axis=1, skipna=True).where(history_count >= min_history)

    # --- Calendar features (cell 4) ---
    df["year"] = df[DATE_COL].dt.year
    df["month"] = df[DATE_COL].dt.month
    df["quarter_num"] = df[DATE_COL].dt.quarter
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

    # --- Derived ratios (cell 4) ---
    if {"consumption_roll_mean_3", "consumption_roll_mean_6"}.issubset(df.columns):
        df["demand_trend_3_vs_6"] = df["consumption_roll_mean_3"] - df["consumption_roll_mean_6"]
    if {"consumption_roll_mean_3", "consumption_roll_mean_12"}.issubset(df.columns):
        df["demand_trend_3_vs_12"] = df["consumption_roll_mean_3"] - df["consumption_roll_mean_12"]
    if "consumption_roll_mean_12" in df.columns:
        df["current_consumption_vs_12m"] = df["consumption"] / (df["consumption_roll_mean_12"].abs() + EPS)
    if {"closeBalance", "consumption_roll_mean_3"}.issubset(df.columns):
        df["inventory_runway_3m"] = df["closeBalance"] / (df["consumption_roll_mean_3"].abs() + EPS)
    if {"received", "consumption"}.issubset(df.columns):
        df["received_to_consumption"] = df["received"] / (df["consumption"].abs() + EPS)

    df["facility_product_observation_count_prior"] = df.groupby(GROUP_COLS).cumcount()

    # --- Product-level and district-product aggregates (cell 5) ---
    # `aggregates`, when given, supplies these month-by-group tables from a
    # startup cache instead of recomputing them from `panel`. Identical
    # values; it only avoids re-reading every facility's rows per request.
    aggregates = aggregates or {}
    df = _add_calendar_lagged_aggregate_features(
        df,
        ["productID"],
        "consumption",
        "product_mean_consumption",
        range(1, 7),
        "mean",
        monthly=aggregates.get("product_mean_consumption"),
    )
    if "district" in df.columns:
        df = _add_calendar_lagged_aggregate_features(
            df,
            ["district", "productID"],
            "consumption",
            "district_product_mean_consumption",
            range(1, 7),
            "mean",
            monthly=aggregates.get("district_product_mean_consumption"),
        )

    for prefix in AGGREGATE_PREFIXES:
        lag3 = [f"{prefix}_lag_{lag}" for lag in range(1, 4) if f"{prefix}_lag_{lag}" in df.columns]
        lag6 = [f"{prefix}_lag_{lag}" for lag in range(1, 7) if f"{prefix}_lag_{lag}" in df.columns]
        if lag3:
            df[f"{prefix}_roll3"] = df[lag3].mean(axis=1, skipna=True)
        if lag6:
            df[f"{prefix}_roll6"] = df[lag6].mean(axis=1, skipna=True)
        if f"{prefix}_roll3" in df.columns and f"{prefix}_roll6" in df.columns:
            df[f"{prefix}_trend_3_vs_6"] = df[f"{prefix}_roll3"] - df[f"{prefix}_roll6"]

    # --- Demand-dynamics features, "Experiment 2" (cell 6) ---
    if "consumption_lag_1" in df.columns:
        df["consumption_growth_1m"] = df["consumption"] - df["consumption_lag_1"]
        df["consumption_growth_rate_1m"] = _safe_ratio(
            df["consumption"] - df["consumption_lag_1"], df["consumption_lag_1"]
        )

    if {"consumption_roll_mean_3", "consumption_roll_mean_6"}.issubset(df.columns):
        df["recent_vs_6m_ratio"] = _safe_ratio(df["consumption_roll_mean_3"], df["consumption_roll_mean_6"])
    if {"consumption_roll_mean_3", "consumption_roll_mean_12"}.issubset(df.columns):
        df["recent_vs_12m_ratio"] = _safe_ratio(df["consumption_roll_mean_3"], df["consumption_roll_mean_12"])

    for window in (3, 6, 12):
        mean_col = f"consumption_roll_mean_{window}"
        std_col = f"consumption_roll_std_{window}"
        if {mean_col, std_col}.issubset(df.columns):
            df[f"consumption_cv_{window}m"] = _safe_ratio(df[std_col], df[mean_col])
        lag_cols = [f"consumption_lag_{lag}" for lag in range(1, window + 1) if f"consumption_lag_{lag}" in df.columns]
        if lag_cols:
            valid_count = df[lag_cols].notna().sum(axis=1)
            zero_count = df[lag_cols].eq(0).sum(axis=1)
            df[f"zero_consumption_rate_{window}m"] = zero_count / valid_count.replace(0, np.nan)

    if "consumption_roll_mean_6" in df.columns:
        df["demand_spike_ratio"] = _safe_ratio(df["consumption"], df["consumption_roll_mean_6"])
    if {"consumption_lag_1", "consumption_lag_3"}.issubset(df.columns):
        df["consumption_momentum_3m"] = df["consumption_lag_1"] - df["consumption_lag_3"]

    # --- Target construction, used only to decide which rows to keep (cell 7) ---
    target, month_start, next_month_start = _compute_target(df)

    if not for_inference:
        has_target = ~pd.isna(target)
        df = df.loc[has_target].copy()
        kept_next_month_start = next_month_start.loc[has_target]
        kept_month_start = month_start.loc[has_target]
        assert (_calendar_month_gap(kept_next_month_start, kept_month_start) == 1).all()
    # for_inference=True: keep every row, including the latest month per
    # series (its target is unknown/NaN by construction) — that row is
    # exactly what we forecast from, so it must not be dropped here.

    feature_columns = (
        RAW_NUMERIC_FEATURES
        + CALENDAR_FEATURES
        + DERIVED_RATIO_FEATURES
        + _dynamic_lag_roll_columns(df.columns)
        + DEMAND_DYNAMICS_FEATURES
    )
    feature_columns = [c for c in dict.fromkeys(feature_columns) if c in df.columns]
    categorical_columns = [c for c in CATEGORICAL_FEATURES if c in df.columns]

    output_columns = KEY_COLUMNS + [c for c in feature_columns + categorical_columns if c not in KEY_COLUMNS]
    result = df[output_columns].reset_index(drop=True)

    _report(result, feature_columns, categorical_columns)

    return result


def build_target(panel: pd.DataFrame) -> pd.DataFrame:
    """Return the key columns plus TARGET_COLUMN for every row that has a
    valid next-calendar-month target — the exact same rule
    build_features(for_inference=False) uses internally to decide which
    rows to keep (notebook cell 7). build_features itself never returns
    the target (by design, so the same output schema serves training and
    inference); training code merges this onto build_features' output on
    the key columns to get y.
    """
    df = _clean_panel(panel)
    target, month_start, next_month_start = _compute_target(df)

    has_target = ~pd.isna(target)
    df = df.loc[has_target].copy()
    df[TARGET_COLUMN] = target[has_target]

    kept_next_month_start = next_month_start.loc[has_target]
    kept_month_start = month_start.loc[has_target]
    assert (_calendar_month_gap(kept_next_month_start, kept_month_start) == 1).all()

    return df[KEY_COLUMNS + [TARGET_COLUMN]].reset_index(drop=True)


def _report(result, feature_columns, categorical_columns):
    all_feature_cols = [c for c in dict.fromkeys(feature_columns + categorical_columns)]
    print(f"build_features output shape: {result.shape}")
    print(f"Feature count (excluding key columns): {len(all_feature_cols)}")

    families = {
        "raw_numeric": RAW_NUMERIC_FEATURES,
        "calendar": CALENDAR_FEATURES,
        "derived_ratios": DERIVED_RATIO_FEATURES,
        "lags_and_rolling": _dynamic_lag_roll_columns(result.columns),
        "demand_dynamics": DEMAND_DYNAMICS_FEATURES,
        "categorical": categorical_columns,
    }

    print("Null count per feature family:")
    for name, cols in families.items():
        present = [c for c in cols if c in result.columns]
        if not present:
            continue
        null_count = int(result[present].isna().sum().sum())
        print(f"  {name}: {null_count} nulls across {len(present)} column(s)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from app.core.config import RAW_DATA

    raw = pd.read_csv(RAW_DATA, low_memory=False)
    features = build_features(raw, for_inference=False)
    print(features.head())
