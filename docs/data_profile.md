# Data Profile

Profiled 1 file(s) in `data/raw/`.

## `Madad_Integrated_Data.csv ✰`

- Detected format: `csv`
- Reader: `pandas.read_csv`
- Reader args: `{'encoding': 'utf-8', 'sep': ',', 'low_memory': False}`
- Needs `low_memory=False` to avoid a DtypeWarning: False
- Shape: 457,225 rows x 34 columns
- Columns: ['hf_pk', 'name1', 'date', 'stockout', 'received', 'consumption', 'closeBalance', 'openBalance', 'lat', 'long', 'quarter', 'productID', 'normAvg', 'normStd', 'date_parsed', 'reported_quarter', 'calendar_quarter', 'source_quarter', 'quarter_mismatch_flag', 'facility_type', 'district', 's5_quarterID', 's5_Q3AIalloc', 's5_popDQ3', 's5_Q2AIalloc', 's5_popDQ2', 's5_ExcelAlloc', 's5_popD', 's5_source_row_count', 's3_item', 's3_national_stock', 's1_available', 's5_available', 's3_available']


### Deep profile: monthly facility-product table

- Row count: 457,225
- Column count: 34

**Columns and dtypes:**

| column | dtype |
|---|---|
| hf_pk | int64 |
| name1 | str |
| date | str |
| stockout | int64 |
| received | int64 |
| consumption | int64 |
| closeBalance | int64 |
| openBalance | int64 |
| lat | float64 |
| long | float64 |
| quarter | str |
| productID | int64 |
| normAvg | float64 |
| normStd | float64 |
| date_parsed | str |
| reported_quarter | str |
| calendar_quarter | str |
| source_quarter | str |
| quarter_mismatch_flag | bool |
| facility_type | str |
| district | str |
| s5_quarterID | int64 |
| s5_Q3AIalloc | float64 |
| s5_popDQ3 | float64 |
| s5_Q2AIalloc | float64 |
| s5_popDQ2 | float64 |
| s5_ExcelAlloc | float64 |
| s5_popD | float64 |
| s5_source_row_count | int64 |
| s3_item | str |
| s3_national_stock | float64 |
| s1_available | bool |
| s5_available | bool |
| s3_available | bool |

**Head (10 rows):**

```
   hf_pk                                           name1        date  stockout  received  consumption  closeBalance  openBalance       lat       long quarter  productID     normAvg     normStd date_parsed reported_quarter calendar_quarter source_quarter  quarter_mismatch_flag facility_type district  s5_quarterID  s5_Q3AIalloc  s5_popDQ3  s5_Q2AIalloc  s5_popDQ2  s5_ExcelAlloc  s5_popD  s5_source_row_count s3_item  s3_national_stock  s1_available  s5_available  s3_available
0    663  Envelope, Dispensing, Plastic, 10cm x 7cm, Pcs  2019-10-01         0         0           59             0           59  9.089409 -12.004670  2019Q4          1  152.030426  228.309369  2019-10-01           2019Q4           2019Q4         2019Q4                  False          MCHP  Bombali             1          26.0        NaN           NaN  21.100892            NaN      NaN                    1     NaN                NaN          True          True         False
1    667  Envelope, Dispensing, Plastic, 10cm x 7cm, Pcs  2019-10-01         0         0           70             0           70  8.903324 -12.045450  2019Q4          1  152.030426  228.309369  2019-10-01           2019Q4           2019Q4         2019Q4                  False           CHP  Bombali             1          47.0        NaN           NaN  56.189831            NaN      NaN                    1     NaN                NaN          True          True         False
2    745  Envelope, Dispensing, Plastic, 10cm x 7cm, Pcs  2019-10-01         1         0           14             0           14  8.807020 -12.081810  2019Q4          1  152.030426  228.309369  2019-10-01           2019Q4           2019Q4         2019Q4                  False           CHP  Bombali             1          34.0        NaN           NaN  16.242442            NaN      NaN                    1     NaN                NaN          True          True         False
3    753  Envelope, Dispensing, Plastic, 10cm x 7cm, Pcs  2019-10-01         0         0          100             0          100  8.791610 -12.060680  2019Q4          1  152.030426  228.309369  2019-10-01           2019Q4           2019Q4         2019Q4                  False           CHP  Bombali             1          35.0        NaN           NaN  16.242442            NaN      NaN                    1     NaN                NaN          True          True         False
4    725  Envelope, Dispensing, Plastic, 10cm x 7cm, Pcs  2019-10-01         0         0          100             0          100  9.032880 -12.048580  2019Q4          1  152.030426  228.309369  2019-10-01           2019Q4           2019Q4         2019Q4                  False          MCHP  Bombali             1          31.0        NaN           NaN  13.942039            NaN      NaN                    1     NaN                NaN          True          True         False
5    702  Envelope, Dispensing, Plastic, 10cm x 7cm, Pcs  2019-10-01         0         0          100             0          100  8.767000 -12.197010  2019Q4          1  152.030426  228.309369  2019-10-01           2019Q4           2019Q4         2019Q4                  False           CHP  Bombali             1          33.0        NaN           NaN  36.284348            NaN      NaN                    1     NaN                NaN          True          True         False
6    708  Envelope, Dispensing, Plastic, 10cm x 7cm, Pcs  2019-10-01         0         0           70           130          200  8.941063 -12.130300  2019Q4          1  152.030426  228.309369  2019-10-01           2019Q4           2019Q4         2019Q4                  False          MCHP  Bombali             1          30.0        NaN           NaN  36.284348            NaN      NaN                    1     NaN                NaN          True          True         False
7    698  Envelope, Dispensing, Plastic, 10cm x 7cm, Pcs  2019-10-01         0         0           50            50          100  8.877301 -11.928580  2019Q4          1  152.030426  228.309369  2019-10-01           2019Q4           2019Q4         2019Q4                  False           CHP  Bombali             1          32.0        NaN           NaN   8.867551            NaN      NaN                    1     NaN                NaN          True          True         False
8    734  Envelope, Dispensing, Plastic, 10cm x 7cm, Pcs  2019-10-01         0         0            0           200          200  8.788270 -11.907659  2019Q4          1  152.030426  228.309369  2019-10-01           2019Q4           2019Q4         2019Q4                  False           CHC  Bombali             1          43.0        NaN           NaN   8.867551            NaN      NaN                    1     NaN                NaN          True          True         False
9    739  Envelope, Dispensing, Plastic, 10cm x 7cm, Pcs  2019-10-01         1         0          100             0          100  8.740825 -11.997281  2019Q4          1  152.030426  228.309369  2019-10-01           2019Q4           2019Q4         2019Q4                  False          MCHP  Bombali             1          39.0        NaN           NaN   8.867551            NaN      NaN                    1     NaN                NaN          True          True         False
```

**Per-column profile:**

| column | nulls | distinct | min | max |
|---|---|---|---|---|
| hf_pk | 0 | 1091 | 0 | 20385 |
| name1 | 0 | 36 |  |  |
| date | 0 | 50 |  |  |
| stockout | 0 | 2 | 0 | 1 |
| received | 0 | 680 | 0 | 100000 |
| consumption | 0 | 2162 | 0 | 48000 |
| closeBalance | 0 | 6554 | 0 | 281880 |
| openBalance | 0 | 6455 | 0 | 282000 |
| lat | 0 | 1091 | 6.9679198 | 9.977067 |
| long | 0 | 1086 | -13.2920704 | -10.3074398 |
| quarter | 0 | 16 |  |  |
| productID | 0 | 36 | 1 | 56 |
| normAvg | 0 | 36 | 1.535043353 | 590.5276487 |
| normStd | 0 | 36 | 14.22613345 | 1469.620942 |
| date_parsed | 0 | 50 |  |  |
| reported_quarter | 0 | 16 |  |  |
| calendar_quarter | 0 | 17 |  |  |
| source_quarter | 0 | 16 |  |  |
| quarter_mismatch_flag | 0 | 2 | False | True |
| facility_type | 0 | 4 |  |  |
| district | 0 | 16 |  |  |
| s5_quarterID | 0 | 16 | 1 | 16 |
| s5_Q3AIalloc | 68139 | 2118 | 0.0 | 23236.0 |
| s5_popDQ3 | 411135 | 476 | 0.0 | 24295.0 |
| s5_Q2AIalloc | 421088 | 103 | 1.0 | 4000.0 |
| s5_popDQ2 | 101250 | 3479 | 0.0047594993886797 | 380.725278361369 |
| s5_ExcelAlloc | 387878 | 232 | 5.08685039370079 | 864382.0 |
| s5_popD | 388561 | 30333 | 0.0317080824047625 | 76335.821583825 |
| s5_source_row_count | 0 | 2 | 1 | 2 |
| s3_item | 331059 | 36 |  |  |
| s3_national_stock | 331059 | 108 | 0.0 | 14296563.0 |
| s1_available | 0 | 1 | True | True |
| s5_available | 0 | 1 | True | True |
| s3_available | 0 | 2 | False | True |

**Date column (`date_parsed`):**

- Parsed range: 2019-10-01 00:00:00 to 2023-11-01 00:00:00
- Unparseable dates: 0
- One row per facility-product-month: yes
- Total missing months across all facility-product series (gaps): 461178
- Distinct facilities: 1091
- Distinct products: 36

**Rows per facility-product (describe):**

```
count    27092.000000
mean        16.876753
std         13.045675
min          1.000000
25%          5.000000
50%         14.000000
75%         27.000000
max         49.000000
```

- Duplicate (facility, product, month) rows: 0

**Balance columns:**

- Negative values in `openBalance`: 0
- Negative values in `received`: 0
- Negative values in `consumption`: 0
- Negative values in `closeBalance`: 0
- Rows where closeBalance != openBalance + received - consumption: 13852
- Share of zero consumption: 11.6017%

---

## Step C — comparison against the notebooks

### 1. Which file and columns does notebook 07 read, and how?

[07_Madad_Final_XGBoost_Test_.ipynb](../Madad_Models_Notebooks/07_Madad_Final_XGBoost_Test_.ipynb),
cell 1–2:

```python
BASE_PATH = Path('/content/drive/MyDrive/Madad for Medical Logistics/Dataset/Dryad_Dataset')
DATA_PATH = BASE_PATH / 'Madad_Integrated_Data.csv'
df = pd.read_csv(DATA_PATH, low_memory=False)
```

It then parses `date_parsed` to datetime and drops rows missing
`date_parsed`, `hf_pk`, `productID`, or `consumption`.

Raw columns it reads directly from the file (everything else it uses —
lags, rolling means, `month_sin`/`month_cos`, growth ratios, etc. — is
engineered inside the notebook from these):

`hf_pk`, `productID`, `date_parsed`, `consumption`, `received`,
`openBalance`, `closeBalance`, `stockout`, `normAvg`, `normStd`,
`facility_type`, `district`.

### 2. Does what I extracted match that, in name, format and columns?

- **Format:** matches exactly — CSV, read with `pd.read_csv(..., low_memory=False)`.
- **Columns:** matches exactly — all 34 columns present, including every
  raw column notebook 07 reads.
- **Row count:** matches exactly — 457,225 rows, the same figure the EDA
  notebook reports for the final integrated dataset.
- **Name:** does **not** match exactly. The archive's own zip entry name is
  `Madad_Integrated_Data.csv ✰` (a trailing space + `✰` character baked
  into the filename inside the zip itself — not something the unpack
  script added). Notebook 07 expects a file literally named
  `Madad_Integrated_Data.csv`. This is a filesystem-naming quirk, not a
  data difference — content is identical.

### 3. What cleaning did the integration notebook already apply?

From [EDA_dataset_Drive_Integrated.ipynb](../Madad_Models_Notebooks/EDA_dataset_Drive_Integrated.ipynb):

- Parsed S2's `date` column to datetime; kept S2 as the unmodified
  "backbone" table (no row drops, no dedup — it verified there were no
  duplicated facility-product-date rows and no negative inventory values,
  so nothing needed removing).
- Replaced S2's own `facility_type`/`district` with the canonical values
  from S1, joined on `hf_pk` (validated one-to-one, no mismatches found).
- Cross-walked all 36 S2/S5 products to S3 item names via normalized-text
  matching, with 2 manually reviewed overrides (`productID` 50, 52).
- Kept S2's originally reported quarter as `source_quarter` and added
  `calendar_quarter` (derived from the date) plus a
  `quarter_mismatch_flag` for the 22,450 rows where they disagree — it
  **flagged**, but did not correct, this mismatch.
- Found 10,908 duplicated facility-product-quarter keys in S5 (exactly 2
  rows each); consolidated to one row per key by summing the two distinct
  Q3 components (`Q3AIalloc`, `popDQ3`) and keeping the first non-null
  value of the other context columns, tracked via `s5_source_row_count`.
- Left-joined S1 facility metadata, consolidated S5, and S3 national stock
  onto the S2 backbone. Left joins mean unmatched rows get nulls
  (`s1_available`/`s5_available`/`s3_available` flag this per row) rather
  than being dropped.
- Did **not**: remove or clip any values, impute any missing
  `s5_*`/`s3_*` fields, or check/reconcile
  `closeBalance = openBalance + received - consumption`.

### 4. Given the profile, is more cleaning needed, or is this ready to use?

**Ready to use as-is for reproducing notebook 07's pipeline** — no
additional joins, drops, or column changes are needed; the file matches
the EDA notebook's stated output exactly (row count, columns, keys).

Two pre-existing data-quality points carry forward unchanged from the
notebooks, not introduced by extraction, worth a decision before modeling:

- **13,852 rows (~3%)** where `closeBalance != openBalance + received -
  consumption`. The EDA notebook never checked this and notebook 07 does
  not filter it out either — so today's baseline silently trains on these
  rows. Reproducing the notebooks exactly means leaving them in; a
  correctness-first `prepare_data.py` would need to explicitly choose
  whether to also leave them in, flag them, or drop them.
- **461,178 missing facility-product-months** out of a fairly short
  history per series (median 14 months, max 49). Notebook 07 already
  handles this correctly with calendar-safe lag functions (lags are
  matched by calendar-month gap, not row distance) — that logic must be
  preserved exactly if the pipeline is reproduced, not simplified to a
  plain `.shift()`.

No negative values, no duplicate (facility, product, month) rows — the
notebook's "no duplicated modeling keys" claim holds.
