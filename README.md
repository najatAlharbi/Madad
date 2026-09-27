# MADAD — Intelligent Medical Inventory Management

MADAD forecasts how much of each medical supply a hospital warehouse will use next
month, flags what will run short, and works out where the missing stock can come from.

It is both a data science project (notebooks, models, evaluation) and a web app (FastAPI
backend + React frontend) that puts those models in front of two kinds of user.

- **Quickstart** — [Running the app](#running-the-app), below.
- **Architecture** — [docs/architecture.md](docs/architecture.md).
- **Model documentation** — [docs/models.md](docs/models.md).
- **Data investigation** — [docs/data_profile.md](docs/data_profile.md).
- **Design system** — [design/design-tokens.md](design/design-tokens.md), [design/screens.md](design/screens.md).

## What it does

1. **Forecast** — three XGBoost quantile models predict next month's consumption per
   facility and product as P10 / P50 / P90.
2. **Detect** — shortfall is `P90 − stock`, surplus is `stock − P90`.
3. **Redistribute** — a two-stage LP matches donors to receivers: first maximise the
   shortage covered, then minimise total distance × quantity.
4. **Explain** — an assistant answers questions using only those numbers.

Two views, no login: a **Hospital Warehouse Manager** who uploads a month and acts on it,
and a read-only **Regulatory Authority** network view built from precomputed results.

---

# Running the app

## Prerequisites

- **Python 3.11+** (developed and verified on 3.13)
- **Node 20+** (verified on 24)
- The dataset zip at the repo root. `data/` and `models/` are git-ignored, so a fresh
  clone builds them locally in the steps below.

## 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
```

Every `python -m app.*` command below runs **from the `backend/` directory** — the
package is `app`, rooted at `backend/app/`, and is not importable from the repo root.

## 2. Data and models

From the repo root:

```bash
python scripts/unpack_data.py      # zip -> data/raw/
python scripts/prepare_data.py     # -> data/processed/panel.parquet + facilities.parquet
cd backend
python -m app.ml.train             # ~5 min on CPU -> models/*.joblib
python -m app.ml.evaluate          # -> reports/metrics.json; exits non-zero if it fails its gates
cd ..
python scripts/export_artifacts.py # authority JSONs + the demo facility month
```

`train` and `evaluate` print their own progress (row counts, per-model timings, the
metrics table). Expect coverage ≈ 81.5%, MAE ≈ 76, WAPE ≈ 54%, R² ≈ 0.31.

`export_artifacts.py` re-checks the artifacts and the metrics gate before it writes
anything, then solves the redistribution LP across the whole test period. **It takes a
while** (8 months × 36 products) — it is a batch job so the authority pages never solve
at request time. The repo ships its output, so you only need to re-run it after
retraining.

Models are trained **once, offline**. The API loads them at startup and never retrains;
a forecast request costs ~0.4s. See [docs/architecture.md](docs/architecture.md).

## 3. Chatbot key (optional)

```bash
cp backend/.env.example backend/.env
```

Put a free [Groq](https://console.groq.com/keys) key in `GROQ_API_KEY`. Without it every
other feature works and `/api/chat` returns a labelled *"LLM not configured"* error — it
never invents an answer.

Check which models your key can actually reach before changing `GROQ_MODEL` — keys differ:

```bash
cd backend && .venv/Scripts/python -c "from groq import Groq; import os; from dotenv import load_dotenv; load_dotenv(); print([m.id for m in Groq(api_key=os.getenv('GROQ_API_KEY')).models.list().data])"
```

## 4. Run both servers

Two terminals:

```bash
# terminal 1 — from backend/
uvicorn app.main:app --reload --port 8000

# terminal 2 — from frontend/
npm install
npm run dev
```

Open **http://localhost:5173**. The Vite dev server proxies `/api` to port 8000, so the
browser sees a single origin and the session cookie works without CORS configuration.

Check the backend alone with:

```bash
curl http://localhost:8000/api/health
```

Then: pick **Hospital Warehouse Manager** → **Upload Data** → **Load demo facility** →
**Run forecast**. You get real model output in about a second.

### What an upload needs

Six columns. Supplies are identified **by name** — managers know
"Folic Acid 5mg", not code `34`:

```csv
facility_id,product_name,month,received,consumption,closing_balance
1047,"Folic Acid 5mg, Tab",2023-11,0,2000,29470
```

Everything else the models need is worked out server-side, so it is never the user's
problem:

| Worked out | How |
|---|---|
| `opening_balance` | `closing + consumption − received` |
| `stockout` | whether the month ended at zero |
| `product_id` | matched from the name, tolerating case, punctuation and partials |
| `facility_type`, `district` | looked up in the facility registry |
| `normAvg`, `normStd` | product constants from the panel |

Verified: the derived values match the stored panel exactly, and forecasts are
**identical** to using the original full-column rows. `GET /api/upload/template` returns
a CSV already listing all 36 supply names, so the spelling always matches.

Column names may differ from the above — you confirm a mapping in step 2.

**New facilities** (never in the dataset) work — add `facility_type` and `district`
columns so the forecast uses this facility's real attributes instead of a training-set
average. Either way, a facility with no stored history is flagged **"Low confidence — no
recent history"** on its forecast, so a thin number is never presented as a solid one.
See `data/test_uploads/new_facility_never_seen_before.csv`.

**Forecasting past the data's range** (the model was trained on Oct 2019–Nov 2023) isn't
something more code can fix — it needs real inventory data for those months. A row dated
far outside the training range gets the same **low-confidence flag**: XGBoost can't
extrapolate a year value it never saw, so the result falls back to defaults rather than
a genuine trend. Keep collecting real monthly reports and retrain
(`python -m app.ml.train`) to extend the model's real range.

### Test data for the warehouse view

`data/test_uploads/` holds five files to upload by hand (regenerate with
`python scripts/make_test_uploads.py`). All are real facility-months, so the forecasts
have genuine history behind them. Each covers **2023-11**, so the app forecasts
**2023-12**.

| File | Facility | What it exercises |
|---|---|---|
| `clean_facility_1047_2023-11.csv` | Hospital, Tonkolili, 24 supplies | Happy path — six columns, every check passes. Well stocked: 22 surplus, 2 at risk |
| `custom_headers_facility_637_2023-11.csv` | CHC, Pujehun | The mapping step — columns named `Site Code`, `Item Description`, `Qty Used`… all matched, flagged low-confidence for you to confirm |
| `with_problems_facility_776_2023-11.csv` | CHC, Kambia, 25 rows | Validation — **blocked** rows for a negative balance, an untracked supply ("Aspirin 300mg") and a duplicate. The other rows still forecast |
| `with_codes_facility_620_2023-11.csv` | CHC, Pujehun | The optional `product_id` column, cross-checked against the name |
| `new_facility_never_seen_before.csv` | **New**, CHC, Bo | A facility not in the dataset at all — supplies its own type/district, gets a real forecast flagged **low confidence** |

The **Load demo facility** button uses `data/demo/facility_780_2023-03.csv` instead — a
facility in a much worse position (5 critical), which better demonstrates the shortage
and transfer flows.

## 5. Tests

```bash
cd backend
python -m pytest -q                  # 65 tests, ~75s
```

The UI is verified in a real browser too — it walks the whole journey, screenshots every
screen, and fails on any console error or failed request. With both servers running:

```bash
cd frontend
npx playwright install chromium      # first time only
node scripts/verify-ui.mjs           # -> frontend/verify-shots/*.png
```

## Sessions are temporary

There is no database and no login. A session lives in the backend's memory for 60
minutes of inactivity, and **restarting the backend ends every session** — by design.
When that happens the API returns HTTP 410 and the UI asks you to run the forecast
again.

---

## The two components

1. **Medical Inventory Forecasting & Redistribution** — the web app and the models
   behind it (sections below).
2. **Visual Medication Verification using NLM20** — a separate computer-vision study
   ([NLM20_Visual_Verification/](NLM20_Visual_Verification/)), not part of the app.

---

# 1. Medical Inventory Forecasting & Redistribution

## Overview

The primary objective of MADAD was achieved through an end-to-end decision-support pipeline integrating next-month demand forecasting, uncertainty-aware deficit and potential-surplus detection, and LP-based inventory redistribution.

Under the modeled assumptions, the optimized redistribution plan could potentially cover 80.65% of the forecasted deficit.

Final Pipeline
Historical Inventory Data → Next-Month Demand Forecasting → Quantile Forecasting (P10/P50/P90) → Predicted Deficit / Potential Surplus → LP Redistribution Recommendations

---

## Dataset

The project uses multiple healthcare supply-chain datasets containing information about healthcare facilities, medical product consumption, inventory levels, national stock, and population-based demand and allocation.

### Dataset Source

- **Dataset:**  
  https://doi.org/10.5061/dryad.h9w0vt4tw

---

### Data Files

The dataset consists of five healthcare supply-chain data sources:

- **S1 — Healthcare Facilities:** Facility metadata, including facility ID, facility type, and district.
- **S2 — Inventory & Consumption:** Monthly facility-product inventory and consumption data and the main dataset used for analysis and integration.
- **S3 — National Stock:** Medical supply stock data across different quarters. Random noise was added to comply with data privacy agreements.
- **S4 — Alternative Data:** Similar to S2, with additional control-product information.
- **S5 — Demand & Allocation:** Population-based demand estimates and allocation decisions for healthcare facilities and products.

> **Note:** S4 was not included in the final integration. The final integrated dataset was built using S1, S2, S3, and S5.

---

## Exploratory Data Analysis

Notebook:

`EDA_dataset_Drive_Integrated_Ver2 (1).ipynb`

The EDA pipeline included:

- Dataset structure and coverage analysis
- Missing value and duplicate checks
- Inventory validity and zero-value analysis
- Distribution and high-value observation analysis
- Stockout analysis across time, products, districts, and facility types
- Facility and hospital coverage analysis
- Cross-dataset facility, product, and temporal validation
- Duplicate-key analysis and consolidation
- Dataset integration and final validation

### Key EDA Findings

#### S1 — Healthcare Facilities

- **1,280 healthcare facilities** across **16 districts**
- **5 facility types**, including **46 hospitals**
- No missing values, duplicated rows, or duplicated facility IDs

#### S2 — Inventory & Consumption

- **457,225 monthly facility-product records**
- **1,091 healthcare facilities**
- **36 medical products**
- Data covers **October 2019 – November 2023**
- No missing values, duplicated records, or negative inventory quantities
- Overall stockout rate: **13.55%** (**61,956 records**)

#### S3 — National Stock

- **340 records** after removing one exact duplicate
- **150 unique medical items** across **4 quarters**
- **10 zero-stock records**
- No missing or negative stock values

#### S5 — Demand & Allocation

- **228,238 records** after removing **1,676 exact duplicates**
- **1,092 healthcare facilities**
- **36 products** across **16 quarters**
- No negative demand or allocation values
- Missing estimates were retained as unavailable values rather than replaced with zeros
- Available population-based demand (`popD`) totaled approximately **52.88 million units** during quarters 12–14

### S5 Duplicate-Key Resolution

S5 contained repeated facility-product-quarter keys. Further analysis showed that some duplicated records represented distinct Q3 demand or allocation components.

Distinct Q3 components were consolidated, while repeated Q2 and baseline values were retained once to prevent double-counting. The original S5 dataset remained unchanged, and the consolidation was performed in a separate analysis table.

---

## Final Integrated Dataset

After EDA, validation, cleaning, and integration, **S2 was used as the main monthly backbone**, while S1, S3, and S5 provided additional facility, national stock, demand, and allocation information.

| Dataset Information | Value |
|---|---:|
| Records | **457,225** |
| Columns | **34** |
| Healthcare Facilities | **1,091** |
| Medical Products | **36** |
| Districts | **16** |
| Time Period | **Oct 2019 – Nov 2023** |

The integration preserved all **457,225 monthly S2 records**.

The final integrated dataset is prepared for:

- Feature engineering
- Demand forecasting
- Stockout risk analysis
- Medical supply allocation
- Redistribution optimization

---

## Forecasting Task

The final modeling task is **next-month medical product demand forecasting**.

For each:

**Facility × Product × Current Month**

the model predicts:

**Consumption in the next calendar month**

The final target variable is:

`target_consumption_next_month`

Only observations with a valid next-calendar-month target were retained, resulting in:

**313,698 eligible forecasting observations**

---
## Chronological Data Split

A chronological split was used to prevent future information from leaking into model training.

| Split | Rows | Period |
|---|---:|---|
| Train | **211,452** | Oct 2019 – Aug 2022 |
| Validation | **39,864** | Sep 2022 – Feb 2023 |
| Final Test | **62,382** | Mar 2023 – Oct 2023 |

## Feature Engineering

### Historical Demand & Inventory
- Consumption lags
- Received lags
- Opening and closing balance lags
- Historical stockout indicators
- Rolling mean and standard deviation windows

### Demand Dynamics
- Recent demand growth
- Recent vs. longer-term demand ratios
- Coefficient of variation
- Zero-consumption rates
- Demand spike ratio
- Demand momentum

### Temporal Features
- Year
- Month
- Quarter
- Cyclical month encoding

### Contextual / Pooled Features
- Facility
- Product
- Facility type
- District
- Product-level lagged demand
- District-product lagged demand

## Models

Five forecasting approaches were compared using the Validation set:

1. Naive 3-Month Rolling Average
2. Random Forest
3. XGBoost Quantile
4. LightGBM Quantile
5. CatBoost Quantile

### Validation Results

| Model | MAE ↓ | RMSE ↓ | WAPE ↓ | R² ↑ |
|---|---:|---:|---:|---:|
| **XGBoost Quantile — P50** | **95.0108** | **323.9083** | **53.14%** | **0.3350** |
| LightGBM Quantile — P50 | 95.0298 | 323.9994 | 53.16% | 0.3346 |
| Random Forest | 115.0936 | 327.0622 | 64.38% | 0.3220 |
| Naive 3M Rolling Average | 118.2048 | 361.3108 | 66.12% | 0.1726 |
| CatBoost Quantile — P50 | 139.7397 | 405.4230 | 78.16% | -0.0418 |

**XGBoost Quantile** was selected as the final model.

It reduced MAE by approximately **19.62%** compared with the Naive 3-Month Rolling Average baseline.

## Quantile Forecasting

Instead of producing only a single demand estimate, the final model predicts three demand quantiles:

- **P10** — lower-demand estimate
- **P50** — median demand forecast
- **P90** — conservative higher-demand estimate

On Validation, XGBoost achieved **80.67% P10–P90 coverage**, close to the nominal 80% prediction interval.

P90 was later used as the conservative planning demand for deficit and potential-surplus detection.

---

## Final Model Evaluation

After model selection, the XGBoost Quantile models were retrained using **Train + Validation** and evaluated once on the previously untouched Final Test set.

| Metric | Final Test |
|---|---:|
| P50 MAE | **76.2740** |
| P50 RMSE | **322.3729** |
| P50 WAPE | **53.68%** |
| P50 R² | **0.3107** |
| P10 Pinball Loss | **12.5628** |
| P50 Pinball Loss | **38.1370** |
| P90 Pinball Loss | **27.9193** |
| P10–P90 Coverage | **81.51%** |

The quantile interval remained well calibrated on unseen data, achieving **81.51% P10–P90 coverage**.

---
## Deficit & Potential Surplus Detection

The final forecasts were compared with available inventory using **P90** as the conservative planning demand.

- `Predicted Deficit = max(P90 - Available Inventory, 0)`
- `Potential Surplus = max(Available Inventory - P90, 0)`

Because the dataset does not provide an explicit clinical safety-stock policy, the term **Potential Surplus** is used rather than confirmed surplus.

### Detection Results

| Metric | Result |
|---|---:|
| Predicted Deficit Rows | **28,461** |
| Potential Surplus Rows | **33,921** |
| Total Predicted Deficit | **≈ 3.43 million units** |
| Total Potential Surplus | **≈ 23.57 million units** |

---

## LP Redistribution Optimization

A Linear Programming (LP) model was used to generate transfer recommendations between facilities.

The optimization was performed independently for each **Product × Month** and followed two objectives:

1. **Maximize the predicted deficit covered.**
2. **Minimize transfer distance while preserving maximum coverage.**

Transfers were constrained by donor surplus, receiver deficit, product and month matching, and no self-transfers.
---
## Final Redistribution Results

| Metric | Result |
|---|---:|
| Predicted deficit before redistribution | **3,429,759 units** |
| Potential surplus before redistribution | **23,574,940 units** |
| Optimized transferred quantity | **2,766,062 units** |
| Remaining unmet demand | **663,697 units** |
| **Forecasted deficit coverage** | **80.65%** |
| Recommended transfer rows | **32,877** |
| Quantity-weighted mean transfer distance | **31.81 km** |
| Median transfer distance | **14.03 km** |


---

# 2. Visual Medication Verification — NLM20

## Overview

The **Visual Medication Verification** component extends MADAD with a computer vision workflow for identifying medications from images of pills inside medication bottles.

The objective is to classify each medication image into its corresponding **National Drug Code (NDC)** class. The predicted NDC can then be linked to medication metadata to support medication identification and verification.

The overall workflow is:

**Pill/Bottle Image → Image Classification → Predicted NDC → Medication Metadata → Verification**

This module is developed as a proof of concept and is separate from the main MADAD inventory forecasting and redistribution pipeline.

---

## Dataset

The experiments use the **Images of Pills Inside Medication Bottles (NLM20)** dataset from the University of Michigan Deep Blue Data repository.

### Dataset Links

- **Dataset:**  
  https://deepblue.lib.umich.edu/data/concern/data_sets/6d56zw997

- **Related Research Paper / DOI:**  
  https://doi.org/10.1038/s41746-021-00483-8

### Dataset Summary

| Attribute | Value |
|---|---:|
| Total Images | 13,955 |
| NDC Classes | 20 |
| Training Images | 8,393 |
| Validation Images | 2,776 |
| Test Images | 2,786 |
| Readable Images | 13,955 |
| Corrupted Images | 0 |
| Exact Duplicate Groups | 0 |
| Cross-Split Duplicate Groups | 0 |
| Smallest Class | 160 images |
| Largest Class | 1,001 images |
| Class Imbalance Ratio | 6.26 |

The dataset contains top-down images of pills inside medication bottles. Each image is associated with an NDC class, making the task a **20-class image classification problem**.

Medication-level metadata can also be linked to the NDC identifier and includes information such as drug name, strength, shape, color, imprint, and size.

---

# Exploratory Data Analysis

The first stage of the project focuses on understanding the image dataset before model development.

Notebook:

`01_MADAD_NLM20_Image_EDA.ipynb`

The EDA pipeline includes:

- Inspecting the dataset directory structure.
- Building an image-level manifest.
- Counting the total number of images.
- Identifying all NDC classes.
- Examining train, validation, and test distributions.
- Measuring class frequencies.
- Visualizing class distributions.
- Inspecting representative medication images.
- Checking image readability.
- Identifying potentially corrupted images.
- Detecting exact duplicate images.
- Checking for duplicate images across dataset splits.
- Checking for conflicting duplicate labels.
- Examining class imbalance.

The EDA confirmed that all **13,955 images were readable** and no corrupted images were identified.

No exact duplicate groups, cross-split duplicate groups, or conflicting NDC duplicate groups were detected.

The class distribution is not completely balanced. Class sizes range from **160 to 1,001 images**, resulting in an imbalance ratio of approximately **6.26**.

### Generated EDA Files

The EDA outputs are stored under:

```text
NLM20_Visual_Verification/nlm20_eda_outputs/
```

The generated files include:

```text
nlm20_class_summary.csv
nlm20_duplicate_group_summary.csv
nlm20_duplicate_report.csv
nlm20_eda_summary.csv
nlm20_image_manifest.csv
nlm20_metadata_20_ndc.csv
```

These files provide reusable summaries of the dataset, image-level information, duplicate checks, class statistics, and NDC metadata.

---

## Data Preprocessing & Training Strategy

Notebook:

`02_MADAD_NLM20_Data_Exploration_and_Preprocessing.ipynb`

Before model training, the NLM20 dataset was explored and prepared to create a consistent pipeline for all deep learning experiments.

The preprocessing and training strategy included:

- Organizing image paths and corresponding NDC labels.
- Exploring NDC-level metadata.
- Reviewing the class distribution across the 20 NDC classes.
- Preparing the training, validation, and test datasets.
- Resizing images and applying model-specific preprocessing.
- Preparing class labels for multiclass classification.
- Creating model-ready input pipelines.
- Applying **class weights** to address class imbalance and give greater importance to underrepresented NDC classes.
- Applying **regular image augmentation** to the training data to increase image diversity and improve generalization.
- Using transfer learning with pretrained MobileNet architectures.
- Evaluating both frozen-backbone and partial fine-tuning strategies.

### Handling Class Imbalance

The NLM20 classes were not equally represented. To reduce model bias toward classes with larger numbers of images, **class weights** were incorporated during training.

This increases the contribution of underrepresented classes to the training loss without changing the original dataset distribution.

### Data Augmentation

Image augmentation was applied **only to the training set** to introduce controlled variations of the original images and improve model generalization.

The validation and test sets were kept unchanged to provide a consistent and unbiased evaluation of model performance.

This preprocessing strategy ensures that all experiments use a consistent representation of the NLM20 images and labels while addressing class imbalance and reducing the risk of overfitting.

## Experimental Workflow

The complete experimental workflow was:

**Dataset Inspection → Image EDA → Data Preprocessing → Class Imbalance Handling → Data Augmentation → Transfer Learning → Validation → Fine-Tuning → Test Evaluation**

Three main deep learning experiments were conducted:

| Experiment | Architecture | Training Strategy |
|---|---|---|
| **Model 1** | MobileNetV1 | Frozen pretrained backbone |
| **Model 2** | MobileNetV2 | Frozen pretrained backbone |
| **Model 3** | MobileNetV1 | Partial fine-tuning of the last 20 layers |

The frozen-backbone experiments were first used as transfer-learning baselines. MobileNetV1 was then further explored using partial fine-tuning, where the final 20 layers were made trainable to allow higher-level visual features to adapt more specifically to the NLM20 medication images.

---

## Experiment 1 — MobileNetV1 Frozen

Notebook:

`03_MADAD_NLM20_MobileNetV1_Frozen.ipynb`

The first experiment uses **MobileNetV1** as a pretrained feature extractor.

The convolutional backbone is kept frozen while the classification component is trained on the 20 NDC classes.

This experiment provides the main transfer-learning baseline for the NLM20 visual medication verification task.

Training history is recorded for:

- Accuracy
- Precision
- Recall
- F1-score
- Loss
- Validation accuracy
- Validation precision
- Validation recall
- Validation F1-score
- Validation loss
- Learning rate

### Validation Performance

| Metric | Score |
|---|---:|
| Accuracy | 89.12% |
| Precision | 89.82% |
| Recall | 89.12% |
| F1-Score | 89.19% |

### Test Performance

| Metric | Score |
|---|---:|
| Accuracy | **89.16%** |
| Precision | **89.93%** |
| Recall | **89.16%** |
| F1-Score | **89.20%** |

The trained MobileNetV1 frozen model is saved as:

```text
models/MobileNetV1_Frozen.keras
```

---

## Experiment 2 — MobileNetV2 Frozen

Notebook:

`04_MADAD_NLM20_MobileNetV2_Frozen.ipynb`

The second experiment evaluates **MobileNetV2** using the same frozen-backbone transfer-learning strategy.

This experiment was conducted to compare MobileNetV2 with the MobileNetV1 baseline for medication image recognition.

### Validation Performance

| Metric | Score |
|---|---:|
| Accuracy | 82.74% |
| Precision | 84.55% |
| Recall | 82.74% |
| Weighted F1-Score | 82.32% |
| Macro F1-Score | 80.11% |

### Test Performance

| Metric | Score |
|---|---:|
| Accuracy | 82.23% |
| Precision | 83.96% |
| Recall | 82.23% |
| Weighted F1-Score | 81.80% |
| Macro F1-Score | 79.75% |

The trained MobileNetV2 model is saved as:

```text
models/MobileNetV2_Frozen.keras
```

---

## Experiment 3 — MobileNetV1 Fine-Tuning

Notebook:

`05_MADAD_NLM20_MobileNetV1_Last20.ipynb`

The third experiment investigates whether partial fine-tuning can improve the MobileNetV1 baseline.

Instead of keeping the entire pretrained feature extractor frozen, the **last 20 layers** are made trainable so that higher-level visual features can adapt more specifically to the NLM20 medication images.

### Validation Performance

| Metric | Score |
|---|---:|
| Accuracy | 88.65% |
| Precision | 89.73% |
| Recall | 88.65% |
| F1-Score | 88.51% |

The fine-tuned model achieved strong performance, although the fully frozen MobileNetV1 experiment produced slightly higher validation accuracy.

---

# Model Comparison

| Model | Validation Accuracy | Validation F1 |
|---|---:|---:|
| **MobileNetV1 Frozen** | **89.12%** | **89.19%** |
| MobileNetV1 — Last 20 Layers | 88.65% | 88.51% |
| MobileNetV2 Frozen | 82.74% | 82.32%* |

\* Weighted F1-score.

Among the evaluated experiments, **MobileNetV1 with a frozen backbone achieved the strongest validation performance**.

It also achieved approximately **89.16% test accuracy**, demonstrating that a lightweight transfer-learning architecture can provide promising performance for NDC-based visual medication classification.

---

# Saved Results

Experimental results are stored separately from the notebooks under:

```text
NLM20_Visual_Verification/results/
```

Current result files include:

```text
MobileNetV1_Training_History.csv
MobileNetV1_Validation_Results.csv
MobileNetV1_Test_Results.csv

MobileNetV2_Training_History.csv
MobileNetV2_Validation_Results.csv
MobileNetV2_Test_Results.csv

MobileNetV1_Last20_Training_History.csv
MobileNetV1_Last20_Validation_Results.csv
```

Keeping the results in CSV format makes the experiments easier to compare, reproduce, and analyze independently from the notebooks.

---

# Saved Models

Trained model artifacts are stored under:

```text
NLM20_Visual_Verification/models/
```

Current saved models:

```text
MobileNetV1_Frozen.keras
MobileNetV2_Frozen.keras
```

---

# Repository Structure

```text
NLM20_Visual_Verification/
│
├── notebooks/
│   ├── 01_MADAD_NLM20_Image_EDA.ipynb
│   ├── 02_MADAD_NLM20_Data_Exploration_and_Preprocessing.ipynb
│   ├── 03_MADAD_NLM20_MobileNetV1_Frozen.ipynb
│   ├── 04_MADAD_NLM20_MobileNetV2_Frozen.ipynb
│   └── 05_MADAD_NLM20_MobileNetV1_Last20.ipynb
│
├── nlm20_eda_outputs/
│   ├── nlm20_class_summary.csv
│   ├── nlm20_duplicate_group_summary.csv
│   ├── nlm20_duplicate_report.csv
│   ├── nlm20_eda_summary.csv
│   ├── nlm20_image_manifest.csv
│   └── nlm20_metadata_20_ndc.csv
│
├── models/
│   ├── MobileNetV1_Frozen.keras
│   └── MobileNetV2_Frozen.keras
│
└── results/
    ├── MobileNetV1_Training_History.csv
    ├── MobileNetV1_Validation_Results.csv
    ├── MobileNetV1_Test_Results.csv
    ├── MobileNetV1_Last20_Training_History.csv
    ├── MobileNetV1_Last20_Validation_Results.csv
    ├── MobileNetV2_Training_History.csv
    ├── MobileNetV2_Validation_Results.csv
    └── MobileNetV2_Test_Results.csv
```

---

# Role within MADAD

The NLM20 module adds a **visual medication verification layer** to the broader MADAD project.

While the main MADAD component focuses on medical inventory forecasting and redistribution, the NLM20 component focuses on identifying medications directly from images.

The two components address complementary tasks:

**Inventory Intelligence → Forecasting, Availability, and Redistribution**

**Visual Medication Verification → Image Classification, NDC Identification, and Medication Verification**

# Repository layout

```
backend/
  app/
    main.py              FastAPI app + routers
    api/                 health, session, upload, forecast, transfers, authority, chat
    core/config.py       every path and setting, env-overridable
    ml/                  features, train, evaluate, predict, rules, redistribute, health
    llm/chat.py          Groq-backed assistant, grounded in the session's forecast
    data/authority/      precomputed network JSONs the authority view serves
  tests/
frontend/
  src/{pages,components,lib,styles}/
design/                  tokens, screens spec, approved mockups, logo
scripts/                 unpack_data, prepare_data, profile_data, export_artifacts
docs/                    models.md, data_profile.md
data/  models/  reports/  git-ignored build outputs (see Quickstart)
```

Paths are defined once in [backend/app/core/config.py](backend/app/core/config.py) and
overridable by environment variable; nothing else in the project hard-codes one.
