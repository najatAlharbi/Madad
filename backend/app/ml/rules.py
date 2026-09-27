"""Convert demand forecasts into MADAD's deficit/potential-surplus decision
layer.

Ports notebook 08 (08_Madad_Shortage_Surplus_Detection.ipynb, cells 6-8):
available inventory and forecasted demand are cleaned (missing values ->
0, clipped to non-negative), then the "conservative planning demand" —
P90 by default — is compared against available stock to flag a predicted
deficit or a potential surplus.

Deviations from the notebook, both driven directly by this module's own
spec rather than chosen independently:

- ``madad_status`` is a two-way split (``'Predicted Deficit'`` /
  ``'Potential Surplus'``), not the notebook's three-way ``np.select``
  with a ``'Balanced'`` default. A row whose stock exactly equals the
  planning demand falls out as ``'Potential Surplus'`` (its deficit is
  not ``> 0``), per the exact rule given.
- ``required_cols`` drops ``date_parsed``: the notebook's predictions CSV
  always had it, but the ``forecast_df`` this module actually receives
  (the output of ``app.ml.predict.forecast``) carries ``month`` instead.
  Nothing in this module depends on the date column, so it is simply not
  required.
- The planning quantile is a parameter (default ``'P90'``), not a
  hardcoded column reference, so switching which quantile drives
  deficit/surplus/severity is a one-line change at the call site. The
  *output* column names (``predicted_deficit_p90``,
  ``potential_surplus_p90``) stay fixed regardless of the parameter —
  they name the current default plan, not whichever column was actually
  passed in, so downstream consumers (dashboards, redistribution) have a
  stable schema to depend on even if the planning quantile changes.
"""

import numpy as np
import pandas as pd


def apply_rules(
    forecast_df: pd.DataFrame,
    stock_col: str = "closeBalance",
    planning_quantile: str = "P90",
) -> pd.DataFrame:
    """Add deficit/surplus/status/severity columns to a forecast frame.

    Args:
        forecast_df: must contain ``hf_pk``, ``productID``, ``stock_col``,
            ``'P50'``, and ``planning_quantile``.
        stock_col: column holding available inventory (e.g. the facility's
            most recent ``closeBalance``).
        planning_quantile: which forecast column is treated as the
            conservative planning demand for deficit/surplus/severity.
            Defaults to ``'P90'`` — change this one default to replan
            against a different quantile everywhere this function is
            called with its default.

    Returns:
        A copy of ``forecast_df`` with these columns added:

        - ``predicted_deficit_p90`` = max(planning_demand - stock, 0)
        - ``potential_surplus_p90`` = max(stock - planning_demand, 0)
        - ``predicted_deficit_p50`` = max(P50_demand - stock, 0) — kept
          for comparison/reporting, per the notebook's own comment.
        - ``madad_status``: ``'Predicted Deficit'`` if
          ``predicted_deficit_p90 > 0``, else ``'Potential Surplus'``.
        - ``severity``: ``'critical'`` if stock < P50 demand,
          ``'at_risk'`` if stock < planning demand (but not critical),
          else ``'surplus'``.
    """
    required_cols = ["hf_pk", "productID", stock_col, "P50", planning_quantile]
    missing_cols = [c for c in required_cols if c not in forecast_df.columns]
    if missing_cols:
        raise ValueError(f"apply_rules: missing required columns: {missing_cols}")

    df = forecast_df.copy()

    for col in (stock_col, "P50", planning_quantile):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    available_inventory = df[stock_col].fillna(0).clip(lower=0)
    forecast_demand_p50 = df["P50"].fillna(0).clip(lower=0)
    forecast_demand_plan = df[planning_quantile].fillna(0).clip(lower=0)

    df["predicted_deficit_p90"] = np.maximum(forecast_demand_plan - available_inventory, 0)
    df["potential_surplus_p90"] = np.maximum(available_inventory - forecast_demand_plan, 0)
    df["predicted_deficit_p50"] = np.maximum(forecast_demand_p50 - available_inventory, 0)

    df["madad_status"] = np.where(
        df["predicted_deficit_p90"] > 0, "Predicted Deficit", "Potential Surplus"
    )

    df["severity"] = np.select(
        [available_inventory < forecast_demand_p50, available_inventory < forecast_demand_plan],
        ["critical", "at_risk"],
        default="surplus",
    )

    print(df["madad_status"].value_counts())

    return df
