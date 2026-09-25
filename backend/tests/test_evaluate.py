"""Regression metrics — in particular that raw MSE is reported, not just
the derived RMSE."""

import numpy as np

from app.ml.evaluate import regression_metrics


def test_mse_is_rmse_squared():
    y_true = np.array([10.0, 20.0, 30.0, 40.0])
    y_pred = np.array([12.0, 18.0, 33.0, 35.0])

    metrics = regression_metrics(y_true, y_pred)

    assert set(metrics) >= {"MAE", "MSE", "RMSE", "WAPE", "R2"}
    assert metrics["MSE"] == np.mean((y_true - y_pred) ** 2)
    assert metrics["RMSE"] == metrics["MSE"] ** 0.5


def test_perfect_predictions_have_zero_error():
    y = np.array([5.0, 15.0, 25.0])
    metrics = regression_metrics(y, y)
    assert metrics["MAE"] == 0.0
    assert metrics["MSE"] == 0.0
    assert metrics["RMSE"] == 0.0


def test_mse_penalises_large_misses_harder_than_mae():
    """One big miss should move MSE proportionally more than MAE — that is
    the entire reason to report both, not just one."""
    y_true = np.array([100.0, 100.0, 100.0, 100.0])
    small_misses = np.array([90.0, 90.0, 90.0, 90.0])
    one_big_miss = np.array([100.0, 100.0, 100.0, 60.0])

    small = regression_metrics(y_true, small_misses)
    big = regression_metrics(y_true, one_big_miss)

    assert small["MAE"] == big["MAE"] == 10.0
    assert big["MSE"] > small["MSE"]
