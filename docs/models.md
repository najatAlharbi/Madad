# Madad Models

How the forecasting and redistribution pipeline works, end to end: where the
data comes from, what the model learns, what its numbers mean, and how to
run it again. See [data_profile.md](data_profile.md) for the full raw-data
investigation this summarizes.

## 1. Data source and cleaning

**Source:** `Madad_Integrated_Data.zip` at the repo root (`data/raw/` after
`python scripts/unpack_data.py`) — a single CSV, already the output of
`Madad_Models_Notebooks/EDA_dataset_Drive_Integrated.ipynb`'s S1+S2+S3+S5
integration. 457,225 monthly facility-product rows, 1,091 facilities, 36
products, 2019-10 through 2023-11.

**Cleaning applied** (`scripts/prepare_data.py`, reproducing notebook 07's
load section exactly — nothing more):

1. Parse `date_parsed` to datetime.
2. Drop rows missing `date_parsed`, `hf_pk`, `productID`, or `consumption`
   (0 rows dropped on the current data — everything already had these).
3. Drop duplicate `(hf_pk, productID, date_parsed)` keys, keeping the first
   (0 found — defensive, in case a future data drop introduces them).
4. Sort by `hf_pk, productID, date_parsed`.

Output: `data/processed/panel.parquet` (the full 34-column panel) and
`data/processed/facilities.parquet` (`hf_pk, facility_type, district,
latitude, longitude` — one row per facility, for redistribution distances).

**Known, deliberately unfixed data-quality issue** (see
`docs/data_profile.md` Step C #4): 13,852 rows (~3%) where
`closeBalance != openBalance + received - consumption`. The notebooks never
checked this and neither does this pipeline — it is carried forward
unchanged, matching what the models were actually trained on.

## 2. Feature families

Built by `backend/app/ml/features.py::build_features()`, a line-for-line
port of notebook 07's feature engineering (cells 2-7 and the `feature_cols`
selection in cell 11) — 141 features + 3 key columns
(`hf_pk`, `productID`, `date_parsed`):

| Family | What it is |
|---|---|
| Calendar-safe lags | Lags 1-12 of `consumption`, `received`, `openBalance`, `closeBalance`, `stockout`, filled only when the previous row is *exactly* that many calendar months earlier (a gap in the series produces a null lag, not a value from further back). |
| Rolling means/stds & history counts | 3/6/12-month rolling mean/std of `consumption`, `received`, `closeBalance` from those lag columns, populated only once a minimum number of them are non-null. Also `stockout_rate_past_{3,6,12}`. |
| Calendar features | `year`, `month`, `quarter_num`, `month_sin`, `month_cos`. |
| Derived ratios | `demand_trend_3_vs_6`, `demand_trend_3_vs_12`, `current_consumption_vs_12m`, `inventory_runway_3m`, `received_to_consumption`, `facility_product_observation_count_prior`. |
| Product / district-product aggregates | Mean consumption lagged 1-6 calendar months at the product level and the (district, product) level, plus 3/6-month rolling means and their trend — computed from *other* rows' months only. |
| Demand-dynamics ("Experiment 2") | `consumption_growth_1m`, `consumption_growth_rate_1m`, `recent_vs_{6,12}m_ratio`, `consumption_cv_{3,6,12}m`, `zero_consumption_rate_{3,6,12}m`, `demand_spike_ratio`, `consumption_momentum_3m`. |
| Raw carried-through | `consumption`, `received`, `openBalance`, `closeBalance`, `normAvg`, `normStd`. |
| Categorical | `hf_pk`, `productID`, `facility_type`, `district` (one-hot encoded at training time). |

One documented deviation: the notebook additionally drops any numeric
feature that is 100% null within its own Train+Validation split. This is
data/split-dependent, not a fixed feature definition, so it is **not**
reproduced — the feature schema is always the full 141 columns, which is
what lets training and inference share one fixed schema. See the module
docstring in `features.py` for the full list of things worth a second look.

## 3. Training

**Command** (from `backend/`, per `README.md`):

```bash
python -m app.ml.train
```

**Runtime** (this machine, CPU, full 313,698-row training set): P10 ~59s,
P50 ~136s, P90 ~114s — about 5 minutes total. `--sample N` trains on the
first N full `(hf_pk, productID)` series for a fast smoke run instead.

Three `XGBRegressor(objective='reg:quantileerror')` models (P10/P50/P90),
hyperparameters locked from notebook 07's own validation and never retyped
in code — written once to `models/locked_final_configs.json` and always
read back from that file. Preprocessing: median-impute numeric features,
most-frequent-impute + one-hot categorical features, fit on the training
split only. Time-based split, not random — `TRAIN_END_MONTH="2023-02"`,
`TEST_START_MONTH="2023-03"`, `TEST_END_MONTH="2023-10"` in
`backend/app/core/config.py`.

Writes to `models/`: `preprocessor.joblib`, `xgb_p10/p50/p90.joblib`,
`feature_config.json` (feature column order, target name, train/test month
ranges, hyperparameters, xgboost/scikit-learn versions),
`locked_final_configs.json`.

The notebook hardcodes `device='cuda'`; this fails outright without a GPU,
and worse, xgboost doesn't raise when CUDA is requested but missing — it
silently falls back to CPU with only a warning. `train.py` and
`predict.py` both probe for a real working GPU and explicitly force
`device='cpu'` if none is found, rather than trusting a device parameter
that may already be lying.

## 4. Metrics — meaning and last value

From `python -m app.ml.evaluate` (`backend/app/ml/evaluate.py`), reproducing
notebook 07 cells 15-16 exactly (clip predictions at zero, then sort
row-wise to enforce non-crossing quantiles, then score). Last run —
62,382 test rows, 2023-03 through 2023-10 — is in `reports/metrics.json`:

| Metric | Meaning | Last value |
|---|---|---|
| P10/P50/P90 coverage | Share of rows where actual consumption fell inside `[P10, P90]`. Target band: 78-84% (an 80%-nominal interval, with slack for model/data noise). | **81.49%** |
| Mean interval width | Average `P90 - P10` — how wide the uncertainty band is; narrower is more decisive, as long as coverage holds. | 223.03 units |
| P10/P50/P90 pinball loss | The quantile loss each model was trained to minimize — lower is better, and only comparable to itself across runs (not across quantiles). | 12.56 / 38.20 / 27.95 |
| P50 MAE | Mean absolute error of the median forecast. | 76.39 |
| P50 MSE | Mean squared error — the raw quantity RMSE is the square root of. Penalizes large misses much harder than MAE, since each error is squared before averaging. | 103,994.96 |
| P50 RMSE | Root mean squared error of the median forecast (√MSE), in the same units as the forecast itself. | 322.48 |
| P50 WAPE | Weighted absolute percentage error — total absolute error divided by total actual consumption. Gate: must be <= 60%. | **53.76%** |
| P50 R2 | Fraction of variance in actual consumption explained by the P50 forecast. | 0.310 |

**Gate:** `evaluate.py` exits non-zero (and `export_artifacts.py` refuses to
publish) if coverage falls outside [78%, 84%] or WAPE exceeds 60% — so a
model that regressed cannot reach the website. Both currently pass.

`reports/metrics.json` also has a per-month breakdown and the ten products
with the largest total P50 absolute error.

## 5. Inference

`backend/app/ml/predict.py`:

- `load_models()` loads the preprocessor, three models, and
  `feature_config.json` once, caches them in module state, forces
  `device='cpu'`, and asserts the installed xgboost version matches the
  one `feature_config.json` recorded the models were trained with.
- `forecast(history_df, target_month)` calls
  `build_features(history_df, for_inference=True)`.

**The `for_inference` flag, and why it matters:** training
(`for_inference=False`) drops every row whose next-calendar-month
consumption isn't known yet — including, for every single series, its own
most recent month (there's no "next month" for it yet). That's correct for
training (you can't train on a target you don't have), but it means the
one row you actually want a forecast *from* — the latest observed month —
is exactly the row training throws away. `for_inference=True` keeps every
row, including that last one, and never requires the target column to
exist. `forecast()` then selects the row at `target_month - 1` per series
and predicts from it. A `low_history` flag marks predictions backed by
fewer than 2 prior months (not from the notebook — a serving-time
heuristic so a near-empty series still gets a forecast via imputation
rather than a special case).

Predictions are stacked P10/P50/P90, sorted row-wise (non-crossing), then
clipped at zero (order doesn't change the result — clipping is monotonic).

**Serving cost.** Feature building is the expensive step, and only because
the product / district-product aggregates read every facility's rows. The
API precomputes those tables once at startup
(`build_aggregates`, passed back in as `build_features(..., aggregates=)`)
and then builds features for a single facility's rows only: **~0.4s per
request instead of ~11s, with byte-identical feature values**. Nothing is
retrained at request time; retraining is the offline command below.

`backend/app/ml/rules.py::apply_rules()` (porting notebook 08) then turns
`P50`/`P90` + available stock (`closeBalance`) into
`predicted_deficit_p90`, `potential_surplus_p90`, `madad_status`
(`'Predicted Deficit'` / `'Potential Surplus'`), and `severity`
(`critical` / `at_risk` / `surplus`). The planning quantile (default P90)
is a parameter, so replanning against a different quantile is a one-line
change.

## 6. Redistribution

`backend/app/ml/redistribute.py::solve_all()` (porting notebook 09), one
two-stage LP per `(productID, month)` group with at least one donor
(surplus) and one receiver (deficit):

1. **Stage 1** maximizes total quantity transferred, subject to each
   donor's surplus, each receiver's deficit, and no self-transfers.
2. **Stage 2** minimizes `sum(quantity * distance_km)`, subject to total
   transferred equalling stage 1's optimum — the same maximum coverage,
   re-routed as cheaply as possible.

Distances: haversine, from `data/processed/facilities.parquet`. Solved
with `pulp` + its default CBC solver (the notebook uses scipy's
`linprog`).

**Parameters:**

- `min_transfer_qty` (default 10): minimum non-zero shipment size, applied
  as a **repair on the solved plan**, not as a constraint.

  A hard minimum is naturally a MILP (one binary per edge), but real
  `(product, month)` groups reach ~750 donors × ~350 receivers (~260k
  edges) and CBC cannot solve that in tractable time — it hung during
  development. The obvious cheaper alternative, banning undersized edges
  and re-solving, was tried and **does not work**: the max-coverage LP is
  massively degenerate, so each re-solve picks a different, equally thin
  set of edges. Measured on one real product-month, the total held at
  5,367 units while ~60 fresh sub-threshold edges appeared every
  iteration; the loop never converged, and bailing out of it returned an
  empty plan for a group that had 92 receivers needing ≥10 units and
  13,376 units of surplus available.

  What it does instead: solve both stages as plain continuous LPs, then
  drop shipments below the minimum. Dropping flow cannot violate a donor
  cap, a receiver cap, or create a self-transfer, so the plan stays
  feasible and every shipment clears the minimum. It costs a little
  coverage, which is printed rather than hidden — e.g. *"113 transfers,
  5,032 units (stage1 max 5,367) | min-qty repair dropped 68 shipment(s),
  335 units"*. Set it to 0 for exactly the notebook's behaviour.

- `max_donors_per_receiver` (default None = every pair, as in the
  notebook): keeps only the N nearest donors per receiver. Used only by
  the batch export (N=25), where the full cross product across 8 months ×
  36 products is a multi-hour job. Since stage 2 minimises distance, the
  pruned donors are ones the optimiser would rarely choose — but it *is*
  an approximation, so the per-facility view leaves it off.
- `max_km` (default `None`): drop candidate edges farther apart than this
  before solving — also the main lever for runtime, since it shrinks the
  edge set. `scripts/export_artifacts.py` uses `max_km=150` to keep the
  full 36-product export tractable.

After every solve: assert no donor shipped over its surplus, no receiver
received over its deficit, no self-transfers, and no shipment below the
minimum — then print the result. Stage 2's total is asserted equal to
stage 1's on the **LP result**, before the min-qty repair deliberately
trims a little coverage; that is the property the two-stage formulation is
about. Groups with no donors or no receivers are skipped and logged, not
treated as an error.

## 7. Retraining

**When:** a new month of data lands (extend `data/raw/`, re-run
`prepare_data.py`), the evaluation gate starts failing, or the feature
engineering changes in `features.py`.

**How**, from the repo root:

```bash
python scripts/unpack_data.py      # only if the raw zip changed
python scripts/prepare_data.py     # rebuild data/processed/panel.parquet
cd backend
python -m app.ml.train             # ~5 min on CPU; writes models/*.joblib
python -m app.ml.evaluate          # writes reports/metrics.json; exits non-zero if it fails its gates
python -m app.ml.health            # sanity-check what's now loaded
cd ..
python scripts/export_artifacts.py # only runs if the new evaluation passes its gates
```

`export_artifacts.py` re-verifies the artifacts and the metrics gate itself
before publishing anything, so a bad retrain can't overwrite the website's
data even if a human skips a step above.
