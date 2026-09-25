# Madad architecture

How the app is put together, and why. For the models themselves see
[models.md](models.md); for the data investigation see
[data_profile.md](data_profile.md).

## The one-line version

One question drives everything: **how much of each supply will this warehouse
use next month, and where can it get what is missing?** Four stages answer it —
forecast, detect, redistribute, explain — and every number the UI shows comes
from one of them.

## Runtime shape

```
 browser (Vite :5173)
     │  /api/* proxied → same-origin, so the session cookie just works
     ▼
 FastAPI (:8000)
     ├── app/api/*        thin HTTP: validation, status codes, cookies
     ├── app/core/
     │     runtime.py     ← loaded ONCE at startup
     │     session_store.py  in-memory, TTL 60 min, LRU 200
     ├── app/ml/          features → predict → rules → redistribute
     └── app/llm/chat.py  grounded answers (Groq)
```

### Loaded once, never per request

`app/core/runtime.py` is the answer to "train once, not per inference". At
startup it loads, and then never rebuilds:

| Loaded once | Why it matters |
|---|---|
| preprocessor + 3 XGBoost models | Deserializing per request would dominate latency |
| `panel.parquet` (457k rows) | Read once, shared read-only |
| **lagged aggregate tables** | The expensive part of feature building |
| facility registry, product names | Lookups for validation and labels |
| authority JSONs | Static network results |

The aggregate tables are the important one. Two of the 141 features are
product-level and district-product mean consumption, lagged 1–6 months.
Computing them reads *every* facility's rows, so a naive per-request
`build_features(panel)` costs ~11s. Precomputing them at startup and passing
them in drops a single-facility forecast to **~0.4s — a 30× speed-up with
byte-identical feature values** (asserted in `tests/test_runtime.py`).

Training stays an explicit offline step (`python -m app.ml.train`). The API
never trains; restart it to pick up new artifacts.

### Request path for a forecast

```
POST /api/forecast/run
  └── pipeline.run_forecast(runtime, facility, month)
        ├── combine facility history + the uploaded month (upload wins on conflict)
        ├── build_features(for_inference=True, aggregates=<cached>)   ~0.4s
        ├── preprocessor.transform  →  3 × model.predict
        ├── clip at 0, sort row-wise  →  P10 ≤ P50 ≤ P90
        └── apply_rules  →  gap, surplus, status, severity
```

`for_inference=True` is load-bearing. Training drops every row whose
next-month target is unknown — including each series' most recent month,
which is exactly the row we forecast *from*. Inference keeps it and never
requires the target column. `tests/test_model.py` asserts the two modes
produce identical features for rows they share.

## Sessions without a database

No login, no database, no Redis. `SessionStore` is a locked dict of
`session_id → Session`, holding the uploaded month, the forecast run, the
transfer plan and chat history. 60-minute TTL swept every 5 minutes, 200-session
LRU cap, 30 chat turns with a running summary line when older turns drop.

The cookie is `HttpOnly`, `SameSite=Lax`. In development the Vite proxy makes
the browser see one origin, so the cookie needs no CORS exemption; the CORS
middleware with an explicit origin list exists for the case where the frontend
is served separately.

**Restarting the backend ends every session on purpose.** Endpoints then return
`410` with `{"error": "session_expired"}`, and `WarehouseShell` renders one
recovery screen for the whole workspace rather than each page failing its own way.

A new forecast run clears the previous run *and* the chat history, so an answer
can never mix numbers from two runs.

## What an upload has to contain

The upload schema is deliberately the smallest set a warehouse manager can
actually know: `facility_id`, `product_name`, `month`, `received`,
`consumption`, `closing_balance`. Supplies go by name, not by the dataset's
internal code.

Three of the model's features are *derived* rather than requested
(`validate_input.derive_optional_fields`): `opening_balance` follows from the
balance identity, `stockout` is whether the month ended at zero, and
`product_id` is resolved from the name against the 36-supply catalogue —
matching on normalised text, tolerating case, punctuation and partials, and
refusing to guess when a partial matches more than one supply. Asking a
manager to retype derivable numbers only creates a chance to get them wrong.

This is verified, not assumed: the derived `opening_balance` and `stockout`
match the stored panel exactly, and a six-column upload produces **identical
forecasts** to the original full-column rows (`test_api.py`,
`test_validate_input.py`). When the user *does* supply `opening_balance`, it
is used as given and the balance-identity check still runs.

## New facilities, and forecasting past the data's range

A facility not in the registry still gets a real forecast — `to_panel_rows`
merges `facility_type`/`district` from the registry, and when that merge
misses (the facility genuinely doesn't exist yet), falls back to the
upload's own `facility_type`/`district` columns if supplied. Without them,
the preprocessor's most-frequent imputer substitutes a training-set
average, which is not wrong exactly, but is not *this* facility's real
attributes either — the `facility_known` check's warning says so and names
the fix.

Either way — a new facility, or a source month with no real observation one
calendar month prior (e.g. a date requested far past the panel's actual
range) — `pipeline.run_forecast` flags the row `low_confidence`. The signal
is `consumption_lag_1` being null: that column is null exactly when there
is nothing real to lag from, which is the same condition in both cases, so
one check catches both. It is not a heuristic invented for the UI; it is
reading the actual feature the model saw.

This is a deliberate refusal to let the model appear to extrapolate: tested
directly, the same real series forecast from 2023 data (P50 180) versus a
fabricated far-future row with the same facility/product (P50 48) diverge
sharply — not from a real trend, but because nearly all 141 features fell
back to medians and XGBoost cannot extrapolate a calendar year it never saw
in training. There is no dataset change that fixes this; it needs real
months of data and a retrain (`python -m app.ml.train`), which the pipeline
already supports end to end.

## Facility display

The source dataset never names individual facilities — only `hf_pk`
(a number), `facility_type` (CHC/CHP/MCHP/Hospital) and `district`. Rather
than show the bare id as the primary label, `components/ui.tsx::facilityLabel`
renders `"{type} · {district} (#{id})"` everywhere a facility appears
(sidebar, forecasts, transfers, authority tables). No name is fabricated.

## Status codes the UI branches on

| Code | Meaning | UI response |
|---|---|---|
| `410 session_expired` | Session gone or backend restarted | "Generate the forecast again" screen |
| `409 no_forecast` | Nothing run yet | Empty state with a link to upload |
| `409 no_facility` | No month loaded | Prompt to upload or load the demo |
| `422 validation_failed` | Upload cannot be used | Show the failing checks |
| `503 llm_not_configured` | No `GROQ_API_KEY` | Labelled notice; **never a fabricated answer** |
| `503 authority_data_missing` | Export not run | Tells you the command to run |

## Redistribution

Per `(product, month)`: stage 1 maximises transferred quantity subject to donor
surplus, receiver deficit and no self-transfers; stage 2 minimises
`Σ quantity × distance_km` subject to stage 1's total. Distances are haversine
from `facilities.parquet`. Solved with PuLP + CBC.

Two MVP parameters extend the notebook: `min_transfer_qty` (default 10) and
`max_distance_km`. A hard minimum shipment size is naturally a MILP, but real
groups reach ~750 donors × ~350 receivers (~260k binaries) and CBC hangs. An
iterative "ban the undersized edges and re-solve" loop was tried and fails too
— the max-coverage LP is degenerate, so each re-solve just picks a different
equally-thin set and the loop never converges. Both stages therefore stay plain
continuous LPs and the minimum is applied as a **repair**: drop shipments below
it, which cannot break any constraint, and report the coverage it cost. See
[models.md](models.md#6-redistribution) for the measured numbers.

The authority view never solves at request time. `scripts/export_artifacts.py`
runs the whole test period offline and writes static JSON.

## The assistant

Grounding, not embeddings. The session's forecast run compacts to JSON, plus
transfer suggestions and the network summary; if it exceeds ~40 KB it keeps the
products the question mentions plus the ten largest gaps. The system prompt
forbids any number not in that context.

`used_context_keys` is computed **server-side from what was actually sent**, not
self-reported by the model — the server knows what it supplied, so it needn't
trust a claim about it.

Without `GROQ_API_KEY` the endpoint returns a labelled 503. It never invents an
answer, and no key ever reaches the browser.

## Frontend

React + Vite + TypeScript, plain CSS driven by the design tokens as CSS
variables. No component library.

- `lib/api.ts` — the only place that talks HTTP; typed responses,
  `SessionExpiredError` and `ApiError` carrying the server's error code.
- `hooks/useForecast.ts` — the forecast run is fetched once and shared by
  context, so four screens don't re-request it.
- `components/ForecastChart.tsx` — the Recharts ComposedChart. The P10–P90
  band is a cone: the last actual month carries a zero-width range so the Area
  has two points to span, otherwise Recharts draws nothing.
- `scripts/verify-ui.mjs` — drives the real browser through the whole journey,
  screenshots each screen, and fails on any console error, failed request or
  missing expected text.

## Testing

| Suite | Covers |
|---|---|
| `test_config.py` | Paths resolve, are absolute, under the repo root |
| `test_rules.py` | Deficit/surplus/severity thresholds |
| `test_model.py` | Train/inference feature parity, monotonic quantiles, golden predictions, cold start |
| `test_runtime.py` | Cached aggregates are byte-identical; runtime loads once |
| `test_validate_input.py` | Every upload check, mapping suggestions |
| `test_session_store.py` | TTL, LRU, chat trimming, forecast reset |
| `test_api.py` | Whole journey against real models; LP invariants; 410/409/503 |
| `frontend/scripts/verify-ui.mjs` | Real browser, all 9 screens, mobile width |
