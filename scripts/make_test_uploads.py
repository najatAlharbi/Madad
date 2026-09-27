"""Generate warehouse-manager test uploads from the real panel.

Four files, each exercising a different part of the upload flow:

  1. clean            — canonical headers, everything valid
  2. custom headers   — same data, renamed columns, to exercise the mapping step
  3. with problems    — deliberate faults, to exercise pass / warning / block
  4. with codes       — the same, plus the optional product_id column

They are written to data/test_uploads/, NOT data/demo/ — the demo loader
globs data/demo/facility_*_*.csv and takes the first, so extra files there
would silently change what "Load demo facility" loads.

Usage (from the repo root):
    python scripts/make_test_uploads.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pandas as pd  # noqa: E402

from app.core.config import PANEL_PARQUET  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "test_uploads"

# Real facilities with a full product list in the panel's last month, so the
# forecast that follows has genuine history behind it.
CLEAN_FACILITY = 1047      # Hospital, Tonkolili
MAPPING_FACILITY = 637     # CHC, Pujehun
PROBLEM_FACILITY = 776     # CHC, Kambia
MONTH = "2023-11"

NAMES_FACILITY = 620       # CHC, Pujehun — the names-only file

# What a different health system's export might call the same fields.
CUSTOM_HEADERS = {
    "facility_id": "Site Code",
    "product_name": "Item Description",
    "month": "Reporting Period",
    "opening_balance": "Opening Stock",
    "received": "Qty Received",
    "consumption": "Qty Used",
    "closing_balance": "Closing Stock",
    "stockout": "Was Stocked Out",
}


def rows_for(panel: pd.DataFrame, facility_id: int) -> pd.DataFrame:
    """One facility-month from the panel, in the canonical upload shape."""
    subset = panel[(panel["hf_pk"] == facility_id) & (panel["date_parsed"] == pd.Timestamp(f"{MONTH}-01"))]
    if subset.empty:
        raise SystemExit(f"No panel rows for facility {facility_id} in {MONTH}")

    return pd.DataFrame(
        {
            # Only the six fields the app asks a manager for. Opening
            # balance, stockout and the internal product code are all
            # derived or resolved server-side.
            "facility_id": subset["hf_pk"].astype(int),
            "product_name": subset["name1"],
            "month": MONTH,
            "received": subset["received"].astype(int),
            "consumption": subset["consumption"].astype(int),
            "closing_balance": subset["closeBalance"].astype(int),
        }
    ).sort_values("product_name").reset_index(drop=True)


def add_problems(frame: pd.DataFrame) -> pd.DataFrame:
    """Seed one of each fault the validator is supposed to catch."""
    broken = frame.copy()

    # block (that row only): negative closing balance
    broken.loc[0, "closing_balance"] = -40

    # block (that row only): negative quantity
    broken.loc[1, "received"] = -15

    # block (that row only): a supply Madad does not track
    broken.loc[2, "product_name"] = "Aspirin 300mg, Tab"

    # block (that row only): duplicate facility + product + month
    broken = pd.concat([broken, broken.iloc[[3]]], ignore_index=True)

    return broken


def write(frame: pd.DataFrame, name: str, note: str) -> None:
    path = OUT_DIR / name
    frame.to_csv(path, index=False)
    print(f"  {name:44} {len(frame):>3} rows   {note}")


def main() -> None:
    if not PANEL_PARQUET.exists():
        raise SystemExit(f"{PANEL_PARQUET} missing — run scripts/prepare_data.py first")

    panel = pd.read_parquet(PANEL_PARQUET)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Writing warehouse-manager test uploads to {OUT_DIR}:")

    clean = rows_for(panel, CLEAN_FACILITY)
    write(clean, f"clean_facility_{CLEAN_FACILITY}_{MONTH}.csv", "all checks pass")

    mapping = rows_for(panel, MAPPING_FACILITY).rename(columns=CUSTOM_HEADERS)
    write(mapping, f"custom_headers_facility_{MAPPING_FACILITY}_{MONTH}.csv", "renamed columns -> mapping step")

    problems = add_problems(rows_for(panel, PROBLEM_FACILITY))
    write(problems, f"with_problems_facility_{PROBLEM_FACILITY}_{MONTH}.csv", "1 warning + 3 blocked rows")

    # Some systems do export an internal code; it is accepted alongside
    # the name, and cross-checked against it.
    with_codes = rows_for(panel, NAMES_FACILITY)
    codes = panel[["name1", "productID"]].drop_duplicates("name1").set_index("name1")["productID"]
    with_codes.insert(1, "product_id", with_codes["product_name"].map(codes).astype(int))
    write(with_codes, f"with_codes_facility_{NAMES_FACILITY}_{MONTH}.csv", "optional product_id column too")

    print(f"\nEach file is one month ({MONTH}), so the app forecasts {pd.Period(MONTH, 'M') + 1}.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
