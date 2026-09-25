"""Build the facility x product x month panel from RAW_DATA.

Reads RAW_DATA with the exact reader call recorded in docs/data_profile.md,
applies the same cleaning notebook 07's load section applies (cell 2 of
07_Madad_Final_XGBoost_Test_.ipynb) — nothing more. docs/data_profile.md
concluded the extracted file is otherwise ready to use: no rows need
dropping for negatives (there are none) or for the closeBalance
reconciliation mismatch (an open, pre-existing data-quality question, not
something the notebooks clean — see docs/data_profile.md Step C #4). This
script does not decide that question either; it only reproduces what the
notebooks already do before modeling.

Writes:
- PANEL_PARQUET: the cleaned facility x product x month panel, all
  columns, sorted by hf_pk, productID, date_parsed.
- data/processed/facilities.parquet: one row per facility (hf_pk,
  facility_type, district, latitude, longitude) for later distance
  calculations.

Usage (from the repo root):
    python scripts/prepare_data.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pandas as pd  # noqa: E402

from app.core.config import FACILITIES_PARQUET, PANEL_PARQUET, RAW_DATA  # noqa: E402

# Reader call recorded in docs/data_profile.md for RAW_DATA.
READ_CSV_ARGS = {"encoding": "utf-8", "sep": ",", "low_memory": False}

# Notebook 07, cell 2: the only columns a row must have a value in to be
# usable at all (it can't be grouped, dated, or trained on without them).
REQUIRED_COLUMNS = ["date_parsed", "hf_pk", "productID", "consumption"]

PANEL_KEY = ["hf_pk", "productID", "date_parsed"]

FACILITY_COLUMNS = {"hf_pk": "hf_pk", "facility_type": "facility_type", "district": "district", "lat": "latitude", "long": "longitude"}


def human_size(num_bytes):
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def main():
    if not RAW_DATA.exists():
        print(f"ERROR: RAW_DATA not found at {RAW_DATA}. Run scripts/unpack_data.py first.")
        sys.exit(1)

    df = pd.read_csv(RAW_DATA, **READ_CSV_ARGS)
    rows_in = len(df)
    print(f"Rows in: {rows_in:,}")

    # Notebook 07, cell 2: parse date_parsed before anything else.
    df["date_parsed"] = pd.to_datetime(df["date_parsed"], errors="coerce")

    # Report why rows are about to be dropped, per required column, before
    # dropping any of them (a row missing more than one shows up in more
    # than one line below — dropna(subset=...) removes it once).
    print("\nRows missing each required column (before dropping):")
    for col in REQUIRED_COLUMNS:
        missing = int(df[col].isna().sum())
        print(f"  {col}: {missing:,}")

    missing_any = df[REQUIRED_COLUMNS].isna().any(axis=1)
    rows_dropped_missing_required = int(missing_any.sum())

    df = df.dropna(subset=REQUIRED_COLUMNS).copy()

    # Defensive: notebooks found zero duplicate (hf_pk, productID,
    # date_parsed) rows in this data (docs/data_profile.md), but a panel
    # builder should not silently mis-key a future run that does have
    # them. Keep the first occurrence and report the count.
    is_duplicate_key = df.duplicated(subset=PANEL_KEY, keep="first")
    rows_dropped_duplicate_key = int(is_duplicate_key.sum())
    df = df.loc[~is_duplicate_key].copy()

    df = df.sort_values(PANEL_KEY).reset_index(drop=True)

    rows_out = len(df)

    print("\nRows dropped and why:")
    print(f"  Missing date_parsed/hf_pk/productID/consumption: {rows_dropped_missing_required:,}")
    print(f"  Duplicate (hf_pk, productID, date_parsed) key: {rows_dropped_duplicate_key:,}")
    print(f"  Total dropped: {rows_in - rows_out:,}")
    print(f"\nRows out: {rows_out:,}")

    print(f"\nMonth range: {df['date_parsed'].min().date()} to {df['date_parsed'].max().date()}")
    print(f"Distinct facilities: {df['hf_pk'].nunique():,}")
    print(f"Distinct products: {df['productID'].nunique():,}")

    PANEL_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PANEL_PARQUET, index=False)
    panel_size = PANEL_PARQUET.stat().st_size
    print(f"\nWrote {PANEL_PARQUET} ({human_size(panel_size)}, {panel_size:,} bytes)")

    # One row per facility, for later distance calculations. facility_type,
    # district, lat, long were confirmed constant per hf_pk with no nulls
    # (checked against this same file) — a plain drop_duplicates is exact,
    # not an approximation.
    facilities = (
        df[list(FACILITY_COLUMNS)]
        .drop_duplicates(subset="hf_pk")
        .rename(columns=FACILITY_COLUMNS)
        .sort_values("hf_pk")
        .reset_index(drop=True)
    )

    FACILITIES_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    facilities.to_parquet(FACILITIES_PARQUET, index=False)
    facilities_size = FACILITIES_PARQUET.stat().st_size
    print(
        f"Wrote {FACILITIES_PARQUET} "
        f"({human_size(facilities_size)}, {facilities_size:,} bytes, {len(facilities):,} facilities)"
    )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
