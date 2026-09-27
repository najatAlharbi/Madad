"""The runtime cache must be a pure speed-up, never a change in output.

If these fail, a served forecast no longer matches what training-time
feature building would have produced.
"""

import numpy as np
import pandas as pd
import pytest

from app.core.config import MODELS_DIR, PANEL_PARQUET
from app.ml.features import build_aggregates, build_features

pytestmark = pytest.mark.skipif(
    not (PANEL_PARQUET.exists() and (MODELS_DIR / "feature_config.json").exists()),
    reason="Needs the panel and trained artifacts.",
)

FACILITY = 780


@pytest.fixture(scope="module")
def panel():
    return pd.read_parquet(PANEL_PARQUET)


@pytest.fixture(scope="module")
def aggregates(panel):
    return build_aggregates(panel)


def test_cached_aggregates_give_identical_features(panel, aggregates):
    """One facility + cached aggregates == the same rows from a full build."""
    full = build_features(panel, for_inference=True)
    slim = build_features(panel[panel["hf_pk"] == FACILITY], for_inference=True, aggregates=aggregates)

    keys = ["hf_pk", "productID", "date_parsed"]
    merged = full.merge(slim, on=keys, suffixes=("_full", "_slim"))
    assert len(merged) == len(slim)

    for column in (c for c in full.columns if c not in keys):
        left, right = merged[f"{column}_full"], merged[f"{column}_slim"]
        if pd.api.types.is_numeric_dtype(left):
            assert np.allclose(
                left.to_numpy(float), right.to_numpy(float), atol=1e-9, equal_nan=True
            ), f"cached aggregates changed {column}"
        else:
            assert (left.astype("string").fillna("~") == right.astype("string").fillna("~")).all(), column


def test_aggregate_tables_cover_both_levels(aggregates):
    assert "product_mean_consumption" in aggregates
    assert "district_product_mean_consumption" in aggregates


def test_runtime_loads_once_and_is_shared():
    from app.core import runtime as runtime_module

    first = runtime_module.load_runtime()
    second = runtime_module.load_runtime()
    assert first is second, "runtime must be cached, not rebuilt per call"
    assert first.loaded_at == second.loaded_at


def test_runtime_exposes_what_the_api_needs():
    from app.core.runtime import load_runtime

    runtime = load_runtime()
    assert len(runtime.feature_columns) == 141
    assert runtime.product_names
    assert runtime.facility_row(FACILITY) is not None
    assert not runtime.facility_history(FACILITY).empty
    # "YYYY-MM", one month after the panel ends.
    assert len(runtime.default_forecast_month) == 7
