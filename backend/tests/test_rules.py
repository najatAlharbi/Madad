import pandas as pd

from app.ml.rules import apply_rules


def _forecast_df():
    # P50=50, P90=100 for every row; only stock (closeBalance) varies.
    return pd.DataFrame(
        {
            "hf_pk": [1, 2, 3],
            "productID": [10, 10, 10],
            "closeBalance": [20, 70, 150],  # below P50, between P50/P90, above P90
            "P10": [10, 10, 10],
            "P50": [50, 50, 50],
            "P90": [100, 100, 100],
        }
    )


def test_row_below_p50_is_critical():
    result = apply_rules(_forecast_df())
    row = result.loc[result["closeBalance"] == 20].iloc[0]

    assert row["severity"] == "critical"
    assert row["predicted_deficit_p90"] > 0
    assert row["predicted_deficit_p50"] > 0


def test_row_between_p50_and_p90_is_at_risk():
    result = apply_rules(_forecast_df())
    row = result.loc[result["closeBalance"] == 70].iloc[0]

    assert row["severity"] == "at_risk"
    assert row["predicted_deficit_p90"] > 0
    assert row["predicted_deficit_p50"] == 0


def test_row_above_p90_is_surplus():
    result = apply_rules(_forecast_df())
    row = result.loc[result["closeBalance"] == 150].iloc[0]

    assert row["severity"] == "surplus"
    assert row["madad_status"] == "Potential Surplus"
    assert row["predicted_deficit_p90"] == 0
    assert row["potential_surplus_p90"] > 0


def test_deficit_and_surplus_never_both_positive():
    result = apply_rules(_forecast_df())
    both_positive = (result["predicted_deficit_p90"] > 0) & (result["potential_surplus_p90"] > 0)
    assert not both_positive.any()


def test_no_negative_outputs():
    result = apply_rules(_forecast_df())
    for col in ("predicted_deficit_p90", "potential_surplus_p90", "predicted_deficit_p50"):
        assert (result[col] >= 0).all()
