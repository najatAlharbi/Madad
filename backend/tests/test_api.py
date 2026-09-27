"""End-to-end API tests against the real models and the real panel.

Skipped when the artifacts aren't built, since these exercise genuine model
output rather than fixtures.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import MODELS_DIR, PANEL_PARQUET

REQUIRED = [
    PANEL_PARQUET,
    MODELS_DIR / "preprocessor.joblib",
    MODELS_DIR / "xgb_p10.joblib",
    MODELS_DIR / "xgb_p50.joblib",
    MODELS_DIR / "xgb_p90.joblib",
    MODELS_DIR / "feature_config.json",
]

pytestmark = pytest.mark.skipif(
    not all(path.exists() for path in REQUIRED),
    reason="Needs the panel and trained artifacts — run prepare_data.py then app.ml.train.",
)


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def warehouse(client):
    """A session that has loaded the demo month and run a forecast."""
    client.post("/api/session", json={"role": "warehouse"})
    demo = client.post("/api/demo/load")
    assert demo.status_code == 200, demo.text
    run = client.post("/api/forecast/run", json={})
    assert run.status_code == 200, run.text
    return run.json()


# --- health ----------------------------------------------------------


def test_health_reports_loaded_artifacts(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["feature_count"] == 141
    assert body["uptime_seconds"] >= 0
    assert "xgboost" in body["versions"]


def test_health_reports_mse_alongside_rmse(client):
    """MAE/RMSE were always in evaluate.py's output; raw MSE must be too."""
    metrics = client.get("/api/health").json()["last_evaluation_metrics"]
    assert metrics is not None
    assert metrics["p50_mse"] == pytest.approx(metrics["p50_rmse"] ** 2, rel=1e-6)


# --- session ---------------------------------------------------------


def test_session_is_created_and_readable(client):
    created = client.post("/api/session", json={"role": "warehouse"}).json()
    assert created["role"] == "warehouse"
    assert client.get("/api/session").json()["active"] is True


def test_endpoints_return_410_without_a_session():
    """A restarted backend must say session_expired, not crash."""
    from app.main import app

    with TestClient(app) as fresh:
        response = fresh.post("/api/forecast/run", json={})
        assert response.status_code == 410
        assert response.json()["detail"]["error"] == "session_expired"


# --- demo + forecast -------------------------------------------------


def test_demo_load_is_flagged_as_demo(client):
    client.post("/api/session", json={"role": "warehouse"})
    body = client.post("/api/demo/load").json()
    assert body["is_demo"] is True
    assert body["facility_id"] == 780
    assert body["stored_rows"] > 0


def test_forecast_returns_real_monotonic_quantiles(warehouse):
    assert warehouse["products"], "expected at least one product"
    for product in warehouse["products"]:
        assert product["p10"] <= product["p50"] <= product["p90"], product["name"]
        assert product["p10"] >= 0
        assert len(product["history"]) == 13


def test_forecast_gap_matches_the_rule(warehouse):
    """gap must be exactly max(P90 - stock, 0)."""
    for product in warehouse["products"]:
        expected = max(product["p90"] - product["stock"], 0)
        assert product["gap"] == pytest.approx(expected, abs=0.05), product["name"]


def test_forecast_severity_matches_the_thresholds(warehouse):
    for product in warehouse["products"]:
        if product["stock"] < product["p50"]:
            assert product["severity"] == "critical"
        elif product["stock"] < product["p90"]:
            assert product["severity"] == "at_risk"
        else:
            assert product["severity"] == "surplus"


def test_forecast_counts_agree_with_the_products(warehouse):
    counts = warehouse["counts"]
    products = warehouse["products"]
    assert counts["total"] == len(products)
    assert counts["critical"] == sum(1 for p in products if p["severity"] == "critical")


def test_forecast_is_fast_enough_for_the_ui(warehouse):
    """The acceptance bar is 10s end to end; the model call is the bulk of it."""
    assert warehouse["generated_in_seconds"] < 5


def test_real_facility_forecast_is_not_flagged_low_confidence(warehouse):
    """A facility with real stored history must never be flagged as if it
    were a default fallback — low_confidence is for missing history only."""
    assert warehouse["facility"]["is_new"] is False
    assert warehouse["counts"]["low_confidence"] == 0
    assert all(not p["low_confidence"] for p in warehouse["products"])


def test_new_facility_uses_its_own_supplied_metadata():
    """A facility never seen before must use ITS OWN facility_type/district
    when the upload supplies them — not a blank, not a training-set average
    silently standing in for this facility's real attributes."""
    from app.main import app

    client = TestClient(app)
    client.post("/api/session", json={"role": "warehouse"})
    csv = (
        "facility_id,product_name,month,received,consumption,closing_balance,facility_type,district\n"
        '424242,"Folic Acid 5mg, Tab",2023-11,0,40,60,CHC,Bo\n'
    )
    mapping = {
        "facility_id": "facility_id", "product_name": "product_name", "month": "month",
        "received": "received", "consumption": "consumption", "closing_balance": "closing_balance",
        "facility_type": "facility_type", "district": "district",
    }
    import json as json_module

    confirmed = client.post(
        "/api/upload/confirm",
        files={"file": ("month.csv", csv, "text/csv")},
        data={"mapping": json_module.dumps(mapping), "use_calculated_closing": "false"},
    )
    assert confirmed.status_code == 200, confirmed.text
    # A brand-new facility has no history, so the "facility recognised"
    # check must warn, not silently pass.
    assert any(c["id"] == "facility_known" and c["level"] == "warning" for c in confirmed.json()["validation"]["checks"])

    run = client.post("/api/forecast/run", json={})
    assert run.status_code == 200
    body = run.json()

    assert body["facility"]["is_new"] is True
    assert body["facility"]["facility_type"] == "CHC"
    assert body["facility"]["district"] == "Bo"
    # A single month of history for a facility that has never been seen
    # before is, honestly, not enough to trust the number.
    assert body["counts"]["low_confidence"] == 1
    assert body["products"][0]["low_confidence"] is True


def test_new_facility_without_metadata_still_forecasts():
    """No facility_type/district supplied — must not crash; the checks say
    what would make the forecast better instead of silently guessing."""
    from app.main import app

    client = TestClient(app)
    client.post("/api/session", json={"role": "warehouse"})
    csv = (
        "facility_id,product_name,month,received,consumption,closing_balance\n"
        '555555,"Folic Acid 5mg, Tab",2023-11,0,40,60\n'
    )
    mapping = {
        "facility_id": "facility_id", "product_name": "product_name", "month": "month",
        "received": "received", "consumption": "consumption", "closing_balance": "closing_balance",
    }
    import json as json_module

    confirmed = client.post(
        "/api/upload/confirm",
        files={"file": ("month.csv", csv, "text/csv")},
        data={"mapping": json_module.dumps(mapping), "use_calculated_closing": "false"},
    )
    assert confirmed.status_code == 200, confirmed.text
    detail = next(c["detail"] for c in confirmed.json()["validation"]["checks"] if c["id"] == "facility_known")
    assert "facility_type and district" in detail

    run = client.post("/api/forecast/run", json={})
    assert run.status_code == 200
    assert run.json()["facility"]["is_new"] is True


def test_results_match_the_run(client, warehouse):
    stored = client.get("/api/forecast/results").json()
    assert stored["forecast_month"] == warehouse["forecast_month"]
    assert len(stored["products"]) == len(warehouse["products"])


def test_forecast_without_data_is_a_409():
    from app.main import app

    with TestClient(app) as fresh:
        fresh.post("/api/session", json={"role": "warehouse"})
        response = fresh.post("/api/forecast/run", json={})
        assert response.status_code == 409
        assert response.json()["detail"]["error"] == "no_facility"


# --- transfers -------------------------------------------------------


def test_transfers_respect_the_lp_invariants(client, warehouse):
    body = client.get("/api/transfers?max_distance_km=150").json()
    for suggestion in body["suggestions"]:
        for donor in suggestion["donors"]:
            assert donor["donor_facility_id"] != body["facility_id"], "self-transfer"
            assert donor["suggested_units"] > 0
            # Every shipment must clear the minimum, or not exist at all.
            assert donor["suggested_units"] >= body["parameters"]["min_transfer_qty"] - 1e-6
            assert donor["distance_km"] <= 150 + 1e-6
            assert donor["suggested_units"] <= donor["spare_units"] + 1e-3
        # Never promise more than the shortage.
        assert suggestion["covered_units"] <= suggestion["gap"] + 1e-3


# --- authority (no session) -------------------------------------------


def test_authority_pages_need_no_session():
    from app.main import app

    with TestClient(app) as anonymous:
        for path in ("/api/authority/overview", "/api/authority/products", "/api/authority/transfers"):
            assert anonymous.get(path).status_code in (200, 503), path


def test_authority_overview_shape(client):
    response = client.get("/api/authority/overview")
    if response.status_code == 503:
        pytest.skip("authority JSONs not exported yet")
    kpis = response.json()["kpis"]
    assert kpis["predicted_shortage_units"] >= 0
    assert 0 <= kpis["coverage_pct"] <= 100


# --- upload ----------------------------------------------------------


def test_template_asks_only_for_what_a_manager_knows(client):
    """Six columns, identified by name — no internal codes, no derivable fields."""
    response = client.get("/api/upload/template")
    assert response.status_code == 200

    lines = response.text.splitlines()
    header = lines[0].split(",")
    assert header == ["facility_id", "product_name", "month", "received", "consumption", "closing_balance"]
    for derivable in ("product_id", "opening_balance", "stockout"):
        assert derivable not in header

    # Pre-filled with the supply names, so spelling always matches.
    assert len(lines) == 37  # header + 36 supplies
    assert "Folic Acid 5mg, Tab" in response.text


def test_products_catalogue_lists_the_tracked_supplies(client):
    body = client.get("/api/products").json()
    assert body["count"] == 36
    assert all(item["name"] for item in body["products"])


def test_upload_suggests_a_mapping(client):
    client.post("/api/session", json={"role": "warehouse"})
    csv = (
        "hf_pk,productID,date,openBalance,received,consumption,closeBalance,stockout\n"
        "780,34,2023-03,104,0,100,4,0\n"
    )
    response = client.post("/api/upload", files={"file": ("month.csv", csv, "text/csv")})
    assert response.status_code == 200
    body = response.json()
    assert body["row_count"] == 1
    assert body["suggested_mapping"]["facility_id"]["column"] == "hf_pk"


def test_upload_confirm_then_forecast(client):
    client.post("/api/session", json={"role": "warehouse"})
    csv = (
        "hf_pk,productID,date,openBalance,received,consumption,closeBalance,stockout\n"
        "780,34,2023-03,104,0,100,4,0\n"
        "780,39,2023-03,80,0,48,32,0\n"
    )
    mapping = {
        "facility_id": "hf_pk", "product_id": "productID", "month": "date",
        "opening_balance": "openBalance", "received": "received", "consumption": "consumption",
        "closing_balance": "closeBalance", "stockout": "stockout",
    }
    import json as json_module

    confirmed = client.post(
        "/api/upload/confirm",
        files={"file": ("month.csv", csv, "text/csv")},
        data={"mapping": json_module.dumps(mapping), "use_calculated_closing": "false"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["is_demo"] is False

    run = client.post("/api/forecast/run", json={})
    assert run.status_code == 200
    assert run.json()["forecast_month"] == "2023-04"


# --- chat ------------------------------------------------------------


def test_chat_history_reports_configuration(client, warehouse):
    body = client.get("/api/chat/history").json()
    assert isinstance(body["configured"], bool)
    assert body["suggested_questions"]
    assert body["can_look_up"]["forecast_run"] is True


def test_chat_without_a_key_is_labelled_not_faked(client, monkeypatch):
    """The endpoint must refuse rather than invent an answer."""
    from app.llm import chat as chat_engine

    monkeypatch.setattr(chat_engine, "GROQ_API_KEY", "")
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "llm_not_configured"
