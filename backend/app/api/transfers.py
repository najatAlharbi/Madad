"""GET /api/transfers — who can cover this facility's shortages.

Runs the notebook-09 LP for the products this facility is short of, against
every other facility's current potential surplus, and returns the donors
ranked by the plan the optimiser actually chose.
"""

from __future__ import annotations

import logging

import pandas as pd
from fastapi import APIRouter, Depends, Query

from app.api.deps import require_forecast, require_session, runtime_dep
from app.core.config import MAX_DISTANCE_KM, MIN_TRANSFER_QTY
from app.core.runtime import Runtime
from app.core.session_store import Session
from app.ml.redistribute import haversine_km, solve_month
from app.ml.rules import apply_rules

logger = logging.getLogger("madad.transfers")

router = APIRouter(tags=["transfers"])

# Cap how many products we solve per request: each is its own LP, and the
# UI only shows the shortages that matter.
MAX_PRODUCTS_SOLVED = 12


def _network_rules(runtime: Runtime, month: str) -> pd.DataFrame:
    """Deficit/surplus for every facility from the precomputed authority run.

    The authority export already solved the whole network for its period; for
    the per-facility view we recompute the network's current position from the
    panel's last known stock, which is what a warehouse manager can act on.
    """
    source_month = (pd.Period(month, freq="M") - 1).to_timestamp()
    latest = runtime.panel.loc[runtime.panel["date_parsed"] == source_month]
    if latest.empty:
        latest = (
            runtime.panel.sort_values("date_parsed")
            .groupby(["hf_pk", "productID"])
            .tail(1)
        )
    return latest


@router.get("/transfers")
def transfers(
    max_distance_km: float | None = Query(default=MAX_DISTANCE_KM, description="Ignore donors farther than this"),
    min_transfer_qty: float = Query(default=MIN_TRANSFER_QTY, description="Smallest shipment worth making"),
    session: Session = Depends(require_session),
    runtime: Runtime = Depends(runtime_dep),
) -> dict:
    """Donors for each of this facility's forecast shortages."""
    forecast = require_forecast(session)
    facility_id = int(forecast["facility"]["id"])
    month = forecast["forecast_month"]

    short_products = [p for p in forecast["products"] if p["gap"] > 0][:MAX_PRODUCTS_SOLVED]
    if not short_products:
        return {
            "facility_id": facility_id,
            "month": month,
            "parameters": {"min_transfer_qty": min_transfer_qty, "max_distance_km": max_distance_km},
            "suggestions": [],
            "message": "No shortages forecast for this month.",
        }

    me = runtime.facility_row(facility_id) or {}
    network = _network_rules(runtime, month)
    suggestions = []

    for product in short_products:
        product_id = product["product_id"]
        rows = network.loc[network["productID"] == product_id, ["hf_pk", "productID", "closeBalance"]].copy()
        if rows.empty:
            continue

        # This facility's own position comes from the forecast, not the panel,
        # so the LP is solving against the numbers the user is looking at.
        rows = rows.loc[rows["hf_pk"] != facility_id]
        rows["P50"] = product["p50"]
        rows["P90"] = product["p90"]
        rows["month"] = month
        network_scored = apply_rules(rows)

        mine = pd.DataFrame(
            [{
                "hf_pk": facility_id,
                "productID": product_id,
                "month": month,
                "closeBalance": product["stock"],
                "P50": product["p50"],
                "P90": product["p90"],
            }]
        )
        mine_scored = apply_rules(mine)

        combined = pd.concat([network_scored, mine_scored], ignore_index=True)
        # Only this facility should be able to receive, so zero out every
        # other facility's deficit before solving.
        combined.loc[combined["hf_pk"] != facility_id, "predicted_deficit_p90"] = 0.0
        combined.loc[combined["hf_pk"] == facility_id, "potential_surplus_p90"] = 0.0

        plan = solve_month(
            combined,
            product_id,
            month,
            min_qty=min_transfer_qty,
            max_km=max_distance_km,
        )

        donors = []
        # An empty plan is a normal outcome (no donor in range, or the whole
        # deficit is under the minimum shipment size) and carries no columns,
        # so it must not reach sort_values.
        ranked = plan.sort_values("transfer_quantity", ascending=False) if not plan.empty else plan
        for _, row in ranked.iterrows():
            donor_id = int(row["donor_hf_pk"])
            donor = runtime.facility_row(donor_id) or {}
            donors.append(
                {
                    "donor_facility_id": donor_id,
                    "district": donor.get("district"),
                    "facility_type": donor.get("facility_type"),
                    "spare_units": round(float(row["donor_potential_surplus_before"]), 1),
                    "suggested_units": round(float(row["transfer_quantity"]), 1),
                    "distance_km": round(float(row["distance_km"]), 1),
                    "far": float(row["distance_km"]) > 50,
                }
            )

        covered = round(sum(d["suggested_units"] for d in donors), 1)
        suggestions.append(
            {
                "product_id": product_id,
                "name": product["name"],
                "gap": product["gap"],
                "severity": product["severity"],
                "covered_units": covered,
                "still_short": round(max(product["gap"] - covered, 0.0), 1),
                "coverage_pct": round(covered / product["gap"] * 100, 1) if product["gap"] else None,
                "donors": donors,
            }
        )

    session.transfer_plan = {"suggestions": suggestions}
    logger.info("transfers facility=%s products=%d", facility_id, len(suggestions))

    return {
        "facility_id": facility_id,
        "district": me.get("district"),
        "month": month,
        "parameters": {"min_transfer_qty": min_transfer_qty, "max_distance_km": max_distance_km},
        "suggestions": suggestions,
    }


@router.get("/transfers/nearest")
def nearest(
    product_id: int = Query(..., description="Supply needed now"),
    quantity: float = Query(..., gt=0, description="Units needed"),
    session: Session = Depends(require_session),
    runtime: Runtime = Depends(runtime_dep),
) -> dict:
    """Emergency search: nearest facilities that can cover a quantity now.

    Deliberately not an LP — an emergency is a ranked list by distance among
    facilities whose current stock can spare the amount, which is what
    somebody on the phone actually needs.
    """
    facility_id = session.facility_id
    if facility_id is None:
        return {"error": "no_facility", "message": "Pick a facility first."}

    me = runtime.facility_row(facility_id) or {}
    latest = (
        runtime.panel.loc[runtime.panel["productID"] == product_id]
        .sort_values("date_parsed")
        .groupby("hf_pk")
        .tail(1)
    )

    options = []
    for _, row in latest.iterrows():
        donor_id = int(row["hf_pk"])
        if donor_id == facility_id or float(row["closeBalance"]) < quantity:
            continue
        donor = runtime.facility_row(donor_id) or {}
        if me.get("latitude") is None or donor.get("latitude") is None:
            continue
        distance = float(
            haversine_km(me["latitude"], me["longitude"], donor["latitude"], donor["longitude"])
        )
        options.append(
            {
                "donor_facility_id": donor_id,
                "district": donor.get("district"),
                "facility_type": donor.get("facility_type"),
                "stock_on_hand": float(row["closeBalance"]),
                "distance_km": round(distance, 1),
                "as_of_month": str(row["date_parsed"].to_period("M")),
            }
        )

    options.sort(key=lambda option: option["distance_km"])
    return {
        "product_id": product_id,
        "name": runtime.product_names.get(product_id, f"Product {product_id}"),
        "quantity_needed": quantity,
        "options": options[:10],
    }
