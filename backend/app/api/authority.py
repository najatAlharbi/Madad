"""Authority view: read-only network picture from precomputed results.

Every endpoint here reads the JSONs written offline by
scripts/export_artifacts.py. No session, no upload, no solving at request
time — the LP over the whole test period is a batch job, not something a
page load should trigger.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import runtime_dep
from app.core.runtime import Runtime

router = APIRouter(tags=["authority"])

MISSING_DETAIL = {
    "error": "authority_data_missing",
    "message": "Precomputed network results are not built yet. Run `python scripts/export_artifacts.py`.",
}


def _require(runtime: Runtime, name: str) -> dict:
    data = runtime.authority.get(name)
    if data is None:
        raise HTTPException(status_code=503, detail=MISSING_DETAIL)
    return data


@router.get("/authority/overview")
def overview(runtime: Runtime = Depends(runtime_dep)) -> dict:
    """Network KPIs: predicted shortage, covered by transfers, needs buying."""
    data = _require(runtime, "overview")
    redistribution = data.get("redistribution", {})

    deficit = redistribution.get("total_deficit_before") or 0.0
    covered = redistribution.get("optimized_transferred") or 0.0

    return {
        "generated_at": data.get("generated_at"),
        "period": data.get("period") or data.get("forecast_month"),
        "facilities": int(runtime.facilities["hf_pk"].nunique()),
        "products": len(runtime.product_names),
        "kpis": {
            "predicted_shortage_units": round(deficit, 1),
            "covered_by_transfers_units": round(covered, 1),
            "needs_procurement_units": round(redistribution.get("remaining_unmet_demand") or 0.0, 1),
            "suggested_transfers": redistribution.get("number_of_transfers"),
            "coverage_pct": round(redistribution.get("coverage_pct") or 0.0, 1),
            "mean_transfer_distance_km": (
                round(redistribution["mean_transfer_distance_km"], 1)
                if redistribution.get("mean_transfer_distance_km") is not None
                else None
            ),
        },
        "status_counts": data.get("status_counts", {}),
        "model": data.get("last_evaluation", {}),
    }


@router.get("/authority/products")
def products(
    filter: str = Query(default="all", pattern="^(all|needs_buying|partly_covered|fixed_by_transfers)$"),
    runtime: Runtime = Depends(runtime_dep),
) -> dict:
    """Per-product coverage, with the filters the Shortages screen offers."""
    data = _require(runtime, "products")
    rows = data.get("products", [])

    enriched = []
    for row in rows:
        deficit = row.get("total_deficit_before") or 0.0
        transferred = row.get("optimized_transferred") or 0.0
        unmet = row.get("remaining_unmet_demand") or 0.0
        coverage = row.get("coverage_pct")

        if deficit <= 0:
            bucket = "fixed_by_transfers"
        elif unmet <= 0:
            bucket = "fixed_by_transfers"
        elif transferred <= 0:
            bucket = "needs_buying"
        else:
            bucket = "partly_covered"

        enriched.append(
            {
                "product_id": row.get("productID"),
                "name": row.get("name1") or runtime.product_names.get(row.get("productID"), "—"),
                "shortage_units": round(deficit, 1),
                "covered_units": round(transferred, 1),
                "still_short_units": round(unmet, 1),
                "coverage_pct": round(coverage, 1) if coverage is not None else None,
                "surplus_units": round(row.get("total_potential_surplus_before") or 0.0, 1),
                "bucket": bucket,
            }
        )

    if filter != "all":
        enriched = [row for row in enriched if row["bucket"] == filter]

    enriched.sort(key=lambda row: -row["still_short_units"])
    return {"generated_at": data.get("generated_at"), "filter": filter, "products": enriched}


@router.get("/authority/transfers")
def transfers(
    limit: int = Query(default=30, ge=1, le=200),
    runtime: Runtime = Depends(runtime_dep),
) -> dict:
    """The largest transfers in the plan, with distances and donor coordinates."""
    data = _require(runtime, "transfers_top")
    rows = data.get("transfers", [])[:limit]

    out = []
    for row in rows:
        product_id = row.get("productID")
        donor = runtime.facility_row(row.get("donor_hf_pk")) or {}
        receiver = runtime.facility_row(row.get("receiver_hf_pk")) or {}
        out.append(
            {
                "product_id": product_id,
                "name": runtime.product_names.get(product_id, f"Product {product_id}"),
                "month": row.get("month"),
                "donor_facility_id": row.get("donor_hf_pk"),
                "donor_district": donor.get("district"),
                "donor_facility_type": donor.get("facility_type"),
                "receiver_facility_id": row.get("receiver_hf_pk"),
                "receiver_district": receiver.get("district"),
                "receiver_facility_type": receiver.get("facility_type"),
                "units": round(row.get("transfer_quantity") or 0.0, 1),
                "distance_km": round(row.get("distance_km") or 0.0, 1),
                "far": (row.get("distance_km") or 0) > 50,
                "donor_lat": row.get("donor_lat"),
                "donor_long": row.get("donor_long"),
                "receiver_lat": row.get("receiver_lat"),
                "receiver_long": row.get("receiver_long"),
            }
        )

    return {"generated_at": data.get("generated_at"), "transfers": out}


@router.get("/authority/metrics")
def metrics(runtime: Runtime = Depends(runtime_dep)) -> dict:
    """The last evaluation's metrics, for the model-quality strip."""
    return _require(runtime, "metrics")
