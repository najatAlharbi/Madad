"""Two-stage LP redistribution, porting notebook 09
(09_Madad_LP_Redistribution.ipynb, cells 7-15).

For every (productID, month) group with at least one donor (potential
surplus) and one receiver (predicted deficit):

- Stage 1 maximizes total transferred quantity, subject to each donor's
  surplus, each receiver's deficit, and no self-transfers.
- Stage 2 minimizes sum(quantity * distance_km), subject to total
  transferred equalling stage 1's optimum — i.e. it re-routes the same
  maximum coverage as cheaply (by distance) as possible.

Distances come from FACILITIES_PARQUET via the haversine formula (same
formula as the notebook).

Deviations from the notebook, both requested rather than chosen
independently:

- The notebook solves both stages as continuous LPs with scipy's
  ``linprog(method='highs')``. This module uses ``pulp`` with its default
  CBC solver instead.
- ``min_qty`` (default 10) is new: the notebook allows any transfer size
  down to a floating-point epsilon. Here, each edge must carry either 0 or
  at least ``min_qty`` units.

  A hard minimum shipment size is naturally a MILP (one binary "is this
  edge used" variable per edge), but real (productID, month) groups here
  reach ~750 donors x ~350 receivers — ~260,000 candidate edges — and CBC
  cannot solve a MILP that size in tractable time. It was observed to hang
  on real data.

  Two cheaper mechanisms were tried and rejected before the current one.
  Banning undersized edges and re-solving does not work: the max-coverage
  LP is massively degenerate, so the re-solve simply picks a different,
  equally thin set of edges. Measured on one real product-month, the total
  held at 5,367 units while ~60 fresh sub-threshold edges appeared on every
  iteration — the loop never converged, and bailing out of it returned an
  empty plan for a group that plainly had a valid one.

  What this module does instead: solve both stages as plain continuous LPs
  (fast at any of these sizes), then **repair** the final plan by dropping
  shipments below ``min_qty``. Dropping flow can never violate a donor
  surplus cap, a receiver deficit cap, or create a self-transfer, so the
  result is always feasible and every returned shipment clears the
  minimum. It costs a little coverage, which ``solve_month`` prints rather
  than hides. Set ``min_qty=0`` to skip the repair and get exactly the
  notebook's behaviour.

  Consequently the "stage 2 total equals stage 1 total" invariant is
  asserted on the LP result, before the repair — that is the property the
  two-stage formulation is actually about.
- ``max_km`` (default None) is also new: candidate edges farther apart
  than this are dropped before either stage runs, so a transfer will
  never be recommended past a distance the caller considers impractical.
  This also helps performance, since it shrinks the edge set up front.
- ``max_donors_per_receiver`` (default None) prunes to the nearest N donors
  per receiver. Only for batch runs over many months; see solve_month.
"""

import numpy as np
import pandas as pd
import pulp

from app.core.config import FACILITIES_PARQUET

TOLERANCE = 1e-7

# CBC's MILP solutions (used whenever min_qty > 0 introduces binary
# variables) carry more floating-point slack than a pure continuous LP —
# a transfer plan summing to a donor's surplus can come back a few
# hundredths off due to solver feasibility tolerances, not a real
# constraint violation. This tolerance is for checks against solved
# values; TOLERANCE above is for "is this quantity meaningfully nonzero".
SOLVER_TOLERANCE = 1e-3

_FACILITIES_CACHE = {}


def _load_facilities():
    if not _FACILITIES_CACHE:
        facilities = pd.read_parquet(FACILITIES_PARQUET)[["hf_pk", "latitude", "longitude"]]
        _FACILITIES_CACHE["facilities"] = facilities
    return _FACILITIES_CACHE["facilities"]


def haversine_km(lat1, lon1, lat2, lon2):
    """Same formula as notebook 09 cell 8."""
    lat1, lon1, lat2, lon2 = (np.radians(v) for v in (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    return 6371.0088 * c


def _solve_lp_once(donors, receivers, edges, active_edges, maximize, distances=None, fixed_total=None):
    """One continuous LP solve over active_edges only (banned edges are
    simply excluded, equivalent to pinning them to 0). maximize=True is
    stage 1 (maximize sum(x)); maximize=False is stage 2 (minimize
    sum(x * distances), with fixed_total pinning the total to stage 1's
    optimum).

    Returns (is_optimal, solution) where solution maps every edge index
    (including banned ones, at 0.0) to its quantity.
    """
    sense = pulp.LpMaximize if maximize else pulp.LpMinimize
    prob = pulp.LpProblem("madad_redistribution", sense)

    x = {e: pulp.LpVariable(f"x_{e}", lowBound=0) for e in active_edges}

    if maximize:
        prob += pulp.lpSum(x.values())
    else:
        prob += pulp.lpSum(x[e] * distances[e] for e in active_edges)

    active = edges.loc[list(active_edges)]

    for d_idx, edge_ids in active.groupby("d_idx").groups.items():
        cap = float(donors.loc[d_idx, "potential_surplus_p90"])
        prob += pulp.lpSum(x[e] for e in edge_ids) <= cap

    for r_idx, edge_ids in active.groupby("r_idx").groups.items():
        cap = float(receivers.loc[r_idx, "predicted_deficit_p90"])
        prob += pulp.lpSum(x[e] for e in edge_ids) <= cap

    if fixed_total is not None:
        # >= rather than == : the donor/receiver caps above already make
        # fixed_total (stage 1's optimum under these exact constraints)
        # an upper bound in practice, so this alone pins the total
        # without risking floating-point infeasibility from an exact
        # equality against a solved value. TOLERANCE is small enough that
        # "gaming" it is not meaningfully different from hitting it
        # exactly (unlike a loose tolerance, which minimizing distance
        # would exploit to ship deliberately less — confirmed by testing).
        prob += pulp.lpSum(x.values()) >= fixed_total - TOLERANCE

    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    is_optimal = pulp.LpStatus[prob.status] == "Optimal"
    solution = {e: 0.0 for e in edges.index}
    solution.update({e: (x[e].value() or 0.0) for e in active_edges})
    return is_optimal, solution


def _apply_min_qty(solution, min_qty):
    """Drop shipments smaller than min_qty from a solved plan.

    Why a repair step and not a constraint loop: the max-coverage LP is
    massively degenerate — thousands of edge sets achieve the same optimal
    total. Banning the undersized edges and re-solving just makes the solver
    pick a different, equally thin set (measured on real data: the total held
    at 5,367 while ~60 fresh sub-threshold edges appeared every round, so the
    loop never converged and eventually returned nothing at all). A hard
    minimum is really a MILP, and at ~200k candidate edges CBC cannot solve
    one in tractable time.

    Dropping instead is always safe: removing flow cannot break a donor
    surplus cap, a receiver deficit cap, or introduce a self-transfer. It
    costs a little coverage, which the caller reports rather than hides.

    Returns (filtered_solution, dropped_units, dropped_edges).
    """
    if min_qty <= 0:
        return solution, 0.0, 0

    filtered = {}
    dropped_units = 0.0
    dropped_edges = 0
    for edge, quantity in solution.items():
        if 0 < quantity < min_qty:
            filtered[edge] = 0.0
            dropped_units += quantity
            dropped_edges += 1
        else:
            filtered[edge] = quantity
    return filtered, dropped_units, dropped_edges


def solve_month(
    rows: pd.DataFrame, product_id, month, min_qty=10, max_km=None, max_donors_per_receiver=None
) -> pd.DataFrame:
    """Solve the two-stage LP for one (productID, month) group.

    Args:
        rows: rows with at least hf_pk, productID, month,
            potential_surplus_p90, predicted_deficit_p90 (the output of
            app.ml.rules.apply_rules). Filtered internally to product_id
            and month, so a caller may pass either a pre-filtered group or
            the full rules_df.
        product_id, month: identify the group (also used to filter rows).
        min_qty: minimum non-zero transfer size (see module docstring).
        max_km: drop candidate edges farther apart than this, if given.
        max_donors_per_receiver: keep only this many nearest donors per
            receiver. Default None = every pair, which is what the notebook
            does. Set it for batch runs over many months: the full cross
            product reaches ~260k edges for the biggest product-months, and
            since stage 2 minimises distance the far donors it prunes are
            the ones the optimiser would almost never choose anyway. It is
            an approximation — a distant donor holding the only remaining
            surplus can be pruned — so leave it off for a single month.

    Returns:
        A transfers DataFrame (possibly empty) with one row per
        recommended shipment.
    """
    group = rows.loc[(rows["productID"] == product_id) & (rows["month"] == month)].copy()

    facilities = _load_facilities()
    group = group.merge(facilities, on="hf_pk", how="left")

    donors = (
        group[(group["potential_surplus_p90"] > TOLERANCE) & group["latitude"].notna() & group["longitude"].notna()]
        .reset_index(drop=True)
    )
    receivers = (
        group[(group["predicted_deficit_p90"] > TOLERANCE) & group["latitude"].notna() & group["longitude"].notna()]
        .reset_index(drop=True)
    )

    if donors.empty or receivers.empty:
        print(f"  [{product_id} | {month}] skipped: no donors or no receivers")
        return pd.DataFrame()

    edge_rows = []
    for d_idx, donor in donors.iterrows():
        for r_idx, receiver in receivers.iterrows():
            if donor["hf_pk"] == receiver["hf_pk"]:
                continue
            distance = float(
                haversine_km(donor["latitude"], donor["longitude"], receiver["latitude"], receiver["longitude"])
            )
            if not np.isfinite(distance):
                continue
            if max_km is not None and distance > max_km:
                continue
            edge_rows.append({"d_idx": d_idx, "r_idx": r_idx, "distance_km": distance})

    if not edge_rows:
        print(f"  [{product_id} | {month}] skipped: no feasible transfer edges")
        return pd.DataFrame()

    edges = pd.DataFrame(edge_rows)

    if max_donors_per_receiver is not None and len(edges) > max_donors_per_receiver:
        edges = (
            edges.sort_values("distance_km")
            .groupby("r_idx", sort=False)
            .head(max_donors_per_receiver)
            .reset_index(drop=True)
        )

    all_edges = set(edges.index)

    # Stage 1: maximise total transferred.
    stage1_ok, stage1_solution = _solve_lp_once(donors, receivers, edges, all_edges, maximize=True)
    if not stage1_ok:
        print(f"  [{product_id} | {month}] skipped: stage 1 LP not optimal")
        return pd.DataFrame()

    stage1_total = float(sum(stage1_solution.values()))
    if stage1_total <= TOLERANCE:
        print(f"  [{product_id} | {month}] skipped: zero optimal transfer")
        return pd.DataFrame()

    # Stage 2: same coverage, least total distance.
    distances = edges["distance_km"].to_dict()
    stage2_ok, stage2_solution = _solve_lp_once(
        donors, receivers, edges, all_edges, maximize=False, distances=distances, fixed_total=stage1_total
    )

    solution = stage2_solution if stage2_ok else stage1_solution
    stage2_total = float(sum(solution.values()))

    # The two-stage invariant is checked on the LP result, before the
    # minimum-shipment repair deliberately removes a little coverage.
    _assert_stage_totals(stage1_total, stage2_total)

    solution, dropped_units, dropped_edges = _apply_min_qty(solution, min_qty)
    shipped_total = float(sum(solution.values()))

    transfer_rows = []
    for e in edges.index:
        qty = solution[e]
        if qty <= TOLERANCE:
            continue
        edge = edges.loc[e]
        donor = donors.loc[edge["d_idx"]]
        receiver = receivers.loc[edge["r_idx"]]
        transfer_rows.append(
            {
                "month": month,
                "productID": product_id,
                "donor_hf_pk": donor["hf_pk"],
                "receiver_hf_pk": receiver["hf_pk"],
                "transfer_quantity": float(qty),
                "distance_km": float(edge["distance_km"]),
                "donor_potential_surplus_before": float(donor["potential_surplus_p90"]),
                "receiver_predicted_deficit_before": float(receiver["predicted_deficit_p90"]),
                "donor_lat": float(donor["latitude"]),
                "donor_long": float(donor["longitude"]),
                "receiver_lat": float(receiver["latitude"]),
                "receiver_long": float(receiver["longitude"]),
            }
        )

    transfers = pd.DataFrame(transfer_rows)

    _assert_invariants(transfers, donors, receivers, min_qty)

    dropped_note = (
        f" | min-qty repair dropped {dropped_edges} shipment(s), {dropped_units:.1f} units"
        if dropped_edges
        else ""
    )
    print(
        f"  [{product_id} | {month}] transfers={len(transfers)} qty={shipped_total:.1f} "
        f"(stage1 max={stage1_total:.1f}, stage2={stage2_total:.1f}){dropped_note}"
    )

    return transfers


def _assert_stage_totals(stage1_total, stage2_total):
    """Stage 2 must re-route stage 1's coverage, not quietly reduce it."""
    assert abs(stage2_total - stage1_total) <= SOLVER_TOLERANCE, (
        f"stage 2 total ({stage2_total}) does not equal stage 1 total ({stage1_total})"
    )


def _assert_invariants(transfers, donors, receivers, min_qty):
    if transfers.empty:
        return

    assert not (transfers["donor_hf_pk"] == transfers["receiver_hf_pk"]).any(), "self-transfer detected"

    if min_qty > 0:
        undersized = transfers.loc[transfers["transfer_quantity"] < min_qty - SOLVER_TOLERANCE]
        assert undersized.empty, f"{len(undersized)} shipment(s) below the {min_qty}-unit minimum"

    sent = transfers.groupby("donor_hf_pk")["transfer_quantity"].sum()
    surplus = donors.set_index("hf_pk")["potential_surplus_p90"]
    over_surplus = sent[(sent - surplus.reindex(sent.index)) > SOLVER_TOLERANCE]
    assert over_surplus.empty, f"donor(s) over surplus: {over_surplus.to_dict()}"

    received = transfers.groupby("receiver_hf_pk")["transfer_quantity"].sum()
    deficit = receivers.set_index("hf_pk")["predicted_deficit_p90"]
    over_deficit = received[(received - deficit.reindex(received.index)) > SOLVER_TOLERANCE]
    assert over_deficit.empty, f"receiver(s) over deficit: {over_deficit.to_dict()}"


def solve_all(rules_df: pd.DataFrame, min_qty=10, max_km=None, max_donors_per_receiver=None):
    """Run solve_month for every (productID, month) group in rules_df.

    Returns:
        transfers: concatenation of every group's transfers.
        product_summary: per-productID totals and coverage_pct.
        month_summary: per-month totals and coverage_pct.
        overall_summary: dict of the whole run's totals (mirrors notebook
            09 cell 13's final_summary).
    """
    grouped = rules_df.groupby(["productID", "month"], sort=True)

    all_transfers = []
    group_results = []

    current_product = None
    product_deficit_running = 0.0
    product_transferred_running = 0.0

    def _flush_product_progress(product_id, deficit, transferred):
        coverage = (transferred / deficit * 100) if deficit > 0 else float("nan")
        print(f"Product {product_id}: coverage {coverage:.1f}%")

    for (product_id, month), group in grouped:
        if current_product is not None and product_id != current_product:
            _flush_product_progress(current_product, product_deficit_running, product_transferred_running)
            product_deficit_running = 0.0
            product_transferred_running = 0.0
        current_product = product_id

        total_deficit = float(group["predicted_deficit_p90"].sum())
        total_surplus = float(group["potential_surplus_p90"].sum())

        if total_deficit <= 0 or total_surplus <= 0:
            group_results.append(
                {
                    "productID": product_id,
                    "month": month,
                    "total_deficit_before": total_deficit,
                    "total_potential_surplus_before": total_surplus,
                    "optimized_transfer_quantity": 0.0,
                    "remaining_unmet_demand": total_deficit,
                    "coverage_pct": 0.0 if total_deficit > 0 else float("nan"),
                }
            )
            product_deficit_running += total_deficit
            continue

        transfers = solve_month(
            group,
            product_id,
            month,
            min_qty=min_qty,
            max_km=max_km,
            max_donors_per_receiver=max_donors_per_receiver,
        )
        transferred = float(transfers["transfer_quantity"].sum()) if not transfers.empty else 0.0
        remaining = max(total_deficit - transferred, 0.0)
        coverage = (transferred / total_deficit * 100) if total_deficit > 0 else float("nan")

        group_results.append(
            {
                "productID": product_id,
                "month": month,
                "total_deficit_before": total_deficit,
                "total_potential_surplus_before": total_surplus,
                "optimized_transfer_quantity": transferred,
                "remaining_unmet_demand": remaining,
                "coverage_pct": coverage,
            }
        )

        product_deficit_running += total_deficit
        product_transferred_running += transferred

        if not transfers.empty:
            all_transfers.append(transfers)

    if current_product is not None:
        _flush_product_progress(current_product, product_deficit_running, product_transferred_running)

    transfers_all = pd.concat(all_transfers, ignore_index=True) if all_transfers else pd.DataFrame()
    group_summary = pd.DataFrame(group_results)

    product_summary = (
        group_summary.groupby("productID", as_index=False)
        .agg(
            total_deficit_before=("total_deficit_before", "sum"),
            total_potential_surplus_before=("total_potential_surplus_before", "sum"),
            optimized_transferred=("optimized_transfer_quantity", "sum"),
            remaining_unmet_demand=("remaining_unmet_demand", "sum"),
        )
        .assign(
            coverage_pct=lambda d: np.where(
                d["total_deficit_before"] > 0, d["optimized_transferred"] / d["total_deficit_before"] * 100, np.nan
            )
        )
        .sort_values("total_deficit_before", ascending=False)
        .reset_index(drop=True)
    )

    month_summary = (
        group_summary.groupby("month", as_index=False)
        .agg(
            total_deficit_before=("total_deficit_before", "sum"),
            total_potential_surplus_before=("total_potential_surplus_before", "sum"),
            optimized_transferred=("optimized_transfer_quantity", "sum"),
            remaining_unmet_demand=("remaining_unmet_demand", "sum"),
        )
        .assign(
            coverage_pct=lambda d: np.where(
                d["total_deficit_before"] > 0, d["optimized_transferred"] / d["total_deficit_before"] * 100, np.nan
            )
        )
        .sort_values("month")
        .reset_index(drop=True)
    )

    total_deficit = float(group_summary["total_deficit_before"].sum())
    total_potential_surplus = float(group_summary["total_potential_surplus_before"].sum())
    total_transferred = float(group_summary["optimized_transfer_quantity"].sum())
    remaining_unmet = float(group_summary["remaining_unmet_demand"].sum())
    coverage_pct = (total_transferred / total_deficit * 100) if total_deficit > 0 else 0.0

    if not transfers_all.empty:
        weighted_distance = (transfers_all["transfer_quantity"] * transfers_all["distance_km"]).sum()
        average_distance = weighted_distance / total_transferred if total_transferred > 0 else float("nan")
        median_distance = float(transfers_all["distance_km"].median())
        number_of_transfers = len(transfers_all)
    else:
        average_distance = float("nan")
        median_distance = float("nan")
        number_of_transfers = 0

    overall_summary = {
        "total_deficit_before": total_deficit,
        "total_potential_surplus_before": total_potential_surplus,
        "optimized_transferred": total_transferred,
        "remaining_unmet_demand": remaining_unmet,
        "coverage_pct": coverage_pct,
        "number_of_transfers": number_of_transfers,
        "mean_transfer_distance_km": average_distance,
        "median_transfer_distance_km": median_distance,
    }

    print("\n=== Overall redistribution summary ===")
    for key, value in overall_summary.items():
        print(f"  {key}: {value}")

    return transfers_all, product_summary, month_summary, overall_summary
