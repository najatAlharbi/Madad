"""Schema and business-rule validation for uploaded stock months.

Two jobs:

1. ``suggest_mapping`` — guess which uploaded column means which canonical
   field, so the user confirms a mapping instead of renaming a spreadsheet.
2. ``validate`` — run the brief's checks, each reported as pass / warning /
   block. Blocks stop the run (or drop the offending rows); warnings are
   shown and the user may proceed.

Canonical upload schema (what the app needs, whatever the file calls it):
    facility_id, product_id, month (YYYY-MM), opening_balance, received,
    consumption, closing_balance, stockout (0/1)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

# What a warehouse manager actually has to supply. Deliberately the
# smallest set the models can work from:
#
#   facility_id      which warehouse
#   product_name     which supply — the name, not an internal code
#   month            which month the record covers
#   received         stock received that month
#   consumption      stock used that month
#   closing_balance  stock left at month end (also the stock the
#                    shortage rule compares the P90 forecast against)
#
# Everything else the models need is derived or joined server-side, so it
# is not the user's problem — see DERIVED_FIELDS and to_panel_rows.
REQUIRED_FIELDS = [
    "facility_id",
    "product_name",
    "month",
    "received",
    "consumption",
    "closing_balance",
]

# Accepted if present, filled in otherwise:
#   product_id       resolved from product_name against the catalogue
#   opening_balance  closing + consumption - received (the balance identity)
#   stockout         1 when the month ended with nothing left
#   facility_type    for a facility not already in the registry, this and
#   district         district are looked up automatically. For a genuinely
#                    NEW facility there is nothing to look up, so both go
#                    to the median/most-common training value instead — not
#                    wrong, exactly, but not this facility's own attributes
#                    either. Supplying them here means a new facility gets
#                    real categorical features instead of a training-set
#                    average standing in for them.
OPTIONAL_FIELDS = ["product_id", "opening_balance", "stockout", "facility_type", "district"]

# A file may identify supplies by either, so long as it uses one of them.
PRODUCT_IDENTIFIERS = ["product_name", "product_id"]

# Header synonyms, lowercased and stripped of non-letters before matching.
# The panel's own column names are included so a file exported from this
# app round-trips without the user re-mapping anything.
SYNONYMS: dict[str, list[str]] = {
    "facility_id": ["facilityid", "hfpk", "facility", "hf", "warehouseid", "site", "siteid"],
    "product_id": ["productid", "product", "itemid", "item", "sku", "commodityid", "itemcode", "productcode"],
    "product_name": ["productname", "name1", "name", "itemname", "description", "commodity", "supply", "medicine", "drug"],
    "month": ["month", "date", "dateparsed", "period", "yearmonth", "reportmonth"],
    "opening_balance": ["openingbalance", "openbalance", "opening", "beginningbalance", "startstock"],
    "received": ["received", "receipts", "quantityreceived", "qtyreceived", "resupply"],
    "consumption": ["consumption", "consumed", "used", "issued", "dispensed", "quantityconsumed"],
    "closing_balance": ["closingbalance", "closebalance", "closing", "endingbalance", "stockonhand", "soh"],
    "stockout": ["stockout", "stockedout", "wasstockout", "outofstock"],
    "facility_type": ["facilitytype", "type", "warehousetype", "sitetype", "category"],
    "district": ["district", "region", "province", "area", "zone"],
}

# Tolerance on closing = opening + received - consumption, per the brief.
BALANCE_TOLERANCE = 1.0

# Warn when a facility-product has thinner history than this.
MIN_HISTORY_MONTHS = 6
HISTORY_WINDOW_MONTHS = 12


def _normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _normalise_product(value: str) -> str:
    """Loose key for matching a typed product name to the catalogue.

    Same spirit as the integration notebook's normalize_product_name:
    lowercase, drop punctuation, collapse whitespace — so
    "Paracetamol (Acetaminophen) 500mg, Tab", "paracetamol 500 mg tab" and
    "PARACETAMOL-500MG TAB" all land on comparable keys.
    """
    text = re.sub(r"[^a-z0-9]+", " ", str(value).lower())
    return " ".join(text.split())


def resolve_product_names(frame: pd.DataFrame, catalogue: dict[int, str]) -> tuple[pd.DataFrame, list[int], list[int]]:
    """Fill product_id from product_name where the id is missing.

    Matching is exact-on-normalised-text first, then a containment fallback
    so a manager can write "Folic Acid 5mg" for
    "Folic Acid 5mg, Tab". Ambiguous partials (matching more than one
    catalogue entry) are deliberately left unresolved rather than guessed —
    silently picking the wrong medicine is worse than asking.

    Returns (frame, unresolved_rows, conflicting_rows), both 1-based.
    """
    if "product_name" not in frame.columns:
        return frame, [], []

    exact = {_normalise_product(name): pid for pid, name in catalogue.items()}

    def lookup(raw_name) -> int | None:
        key = _normalise_product(raw_name)
        if not key:
            return None
        if key in exact:
            return exact[key]
        hits = [pid for norm, pid in exact.items() if key in norm or norm in key]
        return hits[0] if len(hits) == 1 else None

    frame = frame.copy()
    resolved = frame["product_name"].map(lookup)

    unresolved: list[int] = []
    conflicting: list[int] = []

    if "product_id" not in frame.columns:
        frame["product_id"] = resolved
    else:
        for position, (index, row) in enumerate(frame.iterrows(), start=1):
            match = resolved.loc[index]
            given = row["product_id"]
            if pd.isna(given) and match is not None:
                frame.at[index, "product_id"] = match
            elif pd.notna(given) and match is not None and int(given) != int(match):
                conflicting.append(position)

    for position, (index, _) in enumerate(frame.iterrows(), start=1):
        name = frame.at[index, "product_name"]
        if pd.isna(frame.at[index, "product_id"]) and pd.notna(name) and str(name).strip():
            unresolved.append(position)

    return frame, unresolved, conflicting


@dataclass
class Check:
    """One validation result the UI renders as a row."""

    id: str
    level: str          # "pass" | "warning" | "block"
    title: str
    detail: str
    rows: list[int] = field(default_factory=list)   # offending row numbers, 1-based

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "level": self.level,
            "title": self.title,
            "detail": self.detail,
            "row_count": len(self.rows),
            "rows": self.rows[:25],
        }


def suggest_mapping(columns: list[str]) -> dict[str, dict]:
    """Suggest canonical_field -> {column, confidence} for the given headers.

    Exact synonym hits are "high"; substring hits are "low" and are the ones
    the user should actually eyeball. Unmatched fields map to None so the UI
    can show an empty select rather than silently guessing.
    """
    normalised = {column: _normalise(column) for column in columns}
    suggestions: dict[str, dict] = {}
    taken: set[str] = set()

    # Every field the upload understands, required and optional alike —
    # product_id is optional now, but a file that carries one should still
    # have it detected. product_name goes first so a column literally called
    # "product name" is not swallowed by product_id's looser synonyms.
    fields = list(dict.fromkeys(["product_name", *REQUIRED_FIELDS, *OPTIONAL_FIELDS]))
    for field_name in fields:
        options = SYNONYMS[field_name]
        chosen, confidence = None, "none"

        for column, norm in normalised.items():
            if column in taken:
                continue
            if norm in options:
                chosen, confidence = column, "high"
                break

        if chosen is None:
            for column, norm in normalised.items():
                if column in taken:
                    continue
                if any(option in norm or norm in option for option in options):
                    chosen, confidence = column, "low"
                    break

        if chosen is not None:
            taken.add(chosen)
        suggestions[field_name] = {"column": chosen, "confidence": confidence}

    return suggestions


def apply_mapping(raw: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    """Rename uploaded columns to the canonical schema and coerce types."""
    present = {source: target for target, source in mapping.items() if source in raw.columns}
    frame = raw.rename(columns=present)[[c for c in present.values()]].copy()

    for numeric in ("facility_id", "product_id", "opening_balance", "received", "consumption", "closing_balance", "stockout"):
        if numeric in frame.columns:
            frame[numeric] = pd.to_numeric(frame[numeric], errors="coerce")

    if "month" in frame.columns:
        parsed = pd.to_datetime(frame["month"], errors="coerce", format="mixed")
        frame["month"] = parsed.dt.to_period("M").astype("string")

    return frame


def derive_optional_fields(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Fill in the fields the models need but the user shouldn't have to type.

    ``opening_balance`` follows from the balance identity, and ``stockout``
    is simply whether the month ended with nothing left. Both are model
    features, so they must exist by the time features are built — but
    asking a manager to retype derivable numbers only creates a chance to
    get them wrong.

    Returns (frame, names_of_fields_that_were_derived).
    """
    frame = frame.copy()
    derived: list[str] = []

    if "opening_balance" not in frame.columns and {"closing_balance", "consumption", "received"} <= set(frame.columns):
        frame["opening_balance"] = frame["closing_balance"] + frame["consumption"] - frame["received"]
        derived.append("opening_balance")

    if "stockout" not in frame.columns and "closing_balance" in frame.columns:
        frame["stockout"] = (frame["closing_balance"] <= 0).astype(int)
        derived.append("stockout")

    return frame, derived


def validate(
    frame: pd.DataFrame,
    known_facilities: set[int],
    known_products: set[int],
    panel: pd.DataFrame | None = None,
    catalogue: dict[int, str] | None = None,
) -> dict:
    """Run every check against a mapped upload.

    Args:
        frame: output of apply_mapping.
        known_facilities / known_products: the dataset registry.
        panel: historical panel, used only for the history-depth warning.

    Returns:
        {"checks": [...], "blocking": bool, "usable_rows": int,
         "drop_rows": [...], "month": "YYYY-MM" | None}
    """
    checks: list[Check] = []
    drop_rows: set[int] = set()

    # 0. Resolve product codes from names first, so a file that identifies
    # supplies the way a human does still satisfies the product_id
    # requirement below.
    if catalogue and "product_name" in frame.columns:
        frame, unresolved, conflicting = resolve_product_names(frame, catalogue)
        if unresolved:
            drop_rows.update(unresolved)
            checks.append(
                Check(
                    "product_name_match",
                    "block",
                    "Unrecognised supply names",
                    f"{len(unresolved)} row(s) name a supply that is not one of the {len(catalogue)} tracked "
                    "supplies, or name it too vaguely to be sure. Those rows will be skipped.",
                    unresolved,
                )
            )
        elif conflicting:
            checks.append(
                Check(
                    "product_name_match",
                    "warning",
                    "Name and code disagree",
                    f"{len(conflicting)} row(s) have a product code that does not match the product name. "
                    "The code was used.",
                    conflicting,
                )
            )
        else:
            checks.append(
                Check("product_name_match", "pass", "Supply names recognised", "Matched to the tracked supplies")
            )

    # 1. Required columns present — blocking, and nothing else can be judged
    # without them. A supply may be identified by name or by code, so the
    # requirement is "one of the two", not both.
    missing = [f for f in REQUIRED_FIELDS if f not in frame.columns and f not in PRODUCT_IDENTIFIERS]
    if not any(identifier in frame.columns for identifier in PRODUCT_IDENTIFIERS):
        missing.append("product_name")

    if missing:
        checks.append(Check("required_columns", "block", "Required columns missing", f"Not mapped: {', '.join(missing)}"))
        return {
            "checks": [c.to_dict() for c in checks],
            "blocking": True,
            "usable_rows": 0,
            "drop_rows": [],
            "month": None,
            "derived_fields": [],
        }
    checks.append(Check("required_columns", "pass", "All required columns present", f"{len(REQUIRED_FIELDS)} fields mapped"))

    # 2. Fill in what can be worked out, so the user never types it.
    frame, derived = derive_optional_fields(frame)
    if derived:
        explanation = {
            "opening_balance": "opening = closing + consumption − received",
            "stockout": "stockout = month ended with zero stock",
        }
        checks.append(
            Check(
                "derived_fields",
                "pass",
                "Filled in for you",
                "; ".join(explanation[field] for field in derived),
            )
        )

    # apply_mapping normally does this, but validate must not silently pass a
    # frame whose months were never normalised — coerce defensively so an
    # unreadable date is always caught, whoever calls us.
    frame = frame.copy()
    if not pd.api.types.is_string_dtype(frame["month"]) or not frame["month"].dropna().str.fullmatch(r"\d{4}-\d{2}").all():
        frame["month"] = (
            pd.to_datetime(frame["month"], errors="coerce", format="mixed").dt.to_period("M").astype("string")
        )

    row_numbers = pd.Series(range(1, len(frame) + 1), index=frame.index)

    # 2. Month parses, and the upload covers exactly one month.
    bad_month = frame["month"].isna()
    months = sorted(frame.loc[~bad_month, "month"].dropna().unique().tolist())
    if bad_month.any():
        rows = row_numbers[bad_month].tolist()
        drop_rows.update(rows)
        checks.append(Check("month_parse", "block", "Unreadable month values", f"{len(rows)} row(s) have a month that could not be read. Use YYYY-MM.", rows))
    if len(months) > 1:
        checks.append(Check("single_month", "warning", "More than one month in the file", f"Found {', '.join(months)}. The most recent month will be forecast."))
    elif months:
        checks.append(Check("single_month", "pass", "One reporting month", months[0]))
    month = months[-1] if months else None

    # 3. Facility known to the dataset — warning, not a block: we can still
    # forecast, just with no history behind it, and using the columns below
    # instead of a training-set average for its facility type and district.
    unknown_facilities = sorted({int(v) for v in frame["facility_id"].dropna().unique() if int(v) not in known_facilities})
    if unknown_facilities:
        has_own_metadata = {"facility_type", "district"} <= set(frame.columns)
        hint = (
            "Its own facility_type/district will be used."
            if has_own_metadata
            else "Add facility_type and district columns for a more accurate forecast — "
            "otherwise the most common values from the training data are used instead."
        )
        checks.append(
            Check(
                "facility_known",
                "warning",
                "New facility — no history here",
                f"Facility {', '.join(map(str, unknown_facilities[:5]))} has no stored history, so its forecast "
                f"relies on this month alone. {hint}",
            )
        )
    else:
        checks.append(Check("facility_known", "pass", "Facility recognised", "Historical records found"))

    # 4. Product must be one of the 36 — blocking for that row only. Rows
    # already reported under "Unrecognised supply names" are excluded, so a
    # single bad row is not listed twice under two different headings.
    bad_product = ~frame["product_id"].isin(known_products)
    already_reported = row_numbers.isin(drop_rows)
    bad_product = bad_product & ~already_reported
    if bad_product.any():
        rows = row_numbers[bad_product].tolist()
        drop_rows.update(rows)
        checks.append(Check("product_known", "block", "Unknown product codes", f"{len(rows)} row(s) use a product not in the 36 tracked supplies. Those rows will be skipped.", rows))
    elif not already_reported.any():
        checks.append(Check("product_known", "pass", "All products recognised", f"{frame['product_id'].nunique()} supplies"))

    # 5. Balance identity, tolerance 1 unit — warning with an offer to use
    # the calculated value. Skipped when we derived opening_balance from
    # that very identity, where the check could only ever pass.
    expected = frame["opening_balance"] + frame["received"] - frame["consumption"]
    mismatch = (frame["closing_balance"] - expected).abs() > BALANCE_TOLERANCE
    mismatch = mismatch.fillna(False)
    if "opening_balance" in derived:
        pass
    elif mismatch.any():
        rows = row_numbers[mismatch].tolist()
        checks.append(Check("balance_identity", "warning", "Closing balance does not add up", f"{len(rows)} row(s) where closing ≠ opening + received − consumption. You can use the calculated value instead.", rows))
    else:
        checks.append(Check("balance_identity", "pass", "Balances reconcile", "closing = opening + received − consumption"))

    # 6a. No negatives — blocking for those rows.
    quantity_columns = ["opening_balance", "received", "consumption", "closing_balance"]
    negative = (frame[quantity_columns] < 0).any(axis=1)
    if negative.any():
        rows = row_numbers[negative].tolist()
        drop_rows.update(rows)
        checks.append(Check("no_negatives", "block", "Negative quantities", f"{len(rows)} row(s) contain a negative quantity and will be skipped.", rows))
    else:
        checks.append(Check("no_negatives", "pass", "No negative quantities", "All quantities are zero or above"))

    # 6b. No duplicate facility+product rows — blocking for the duplicates.
    duplicated = frame.duplicated(subset=["facility_id", "product_id", "month"], keep="first")
    if duplicated.any():
        rows = row_numbers[duplicated].tolist()
        drop_rows.update(rows)
        checks.append(Check("no_duplicates", "block", "Duplicate rows", f"{len(rows)} repeated facility+product row(s) will be skipped; the first is kept.", rows))
    else:
        checks.append(Check("no_duplicates", "pass", "No duplicate rows", "One row per supply"))

    # 7. History depth — warning only.
    if panel is not None and month:
        target = pd.Period(month, freq="M")
        window_start = target - HISTORY_WINDOW_MONTHS
        facility_ids = frame["facility_id"].dropna().unique().tolist()
        history = panel.loc[panel["hf_pk"].isin(facility_ids)].copy()
        if history.empty:
            checks.append(Check("history_depth", "warning", "No stored history", "Forecasts for this facility rely on defaults and will be weaker."))
        else:
            periods = history["date_parsed"].dt.to_period("M")
            in_window = history.loc[(periods > window_start) & (periods < target)]
            months_present = in_window["date_parsed"].dt.to_period("M").nunique()
            if months_present < MIN_HISTORY_MONTHS:
                checks.append(Check("history_depth", "warning", "Thin history", f"Only {months_present} of the last {HISTORY_WINDOW_MONTHS} months are stored (want {MIN_HISTORY_MONTHS}+). Expect a weaker forecast."))
            else:
                checks.append(Check("history_depth", "pass", "Enough history", f"{months_present} of the last {HISTORY_WINDOW_MONTHS} months available"))

    usable = len(frame) - len(drop_rows)
    return {
        "checks": [c.to_dict() for c in checks],
        # Only a truly unusable file blocks the run: row-level blocks just
        # drop their rows, so a mostly-good file still forecasts.
        "blocking": usable <= 0 or any(c.level == "block" and c.id in {"required_columns", "month_parse"} and not c.rows for c in checks),
        "usable_rows": usable,
        "drop_rows": sorted(drop_rows),
        "month": month,
        "derived_fields": derived,
    }


def to_panel_rows(frame: pd.DataFrame, drop_rows: list[int], runtime) -> pd.DataFrame:
    """Convert validated upload rows into panel-shaped rows for build_features.

    Applies the same resolution and derivation validate() reported on — the
    caller passes the mapped frame, not validate's internal copy — and then
    supplies the model features an uploader cannot know: facility_type and
    district from the facility registry, normAvg / normStd as product-level
    constants from the panel. Joining the real values beats letting the
    preprocessor impute a median.
    """
    if "product_name" in frame.columns:
        frame, _, _ = resolve_product_names(frame, runtime.product_names)
    frame, _ = derive_optional_fields(frame)

    keep = frame.drop(index=[frame.index[r - 1] for r in drop_rows if 0 < r <= len(frame)], errors="ignore")
    keep = keep[keep["product_id"].notna()]

    rows = pd.DataFrame(
        {
            "hf_pk": keep["facility_id"].astype("int64"),
            "productID": keep["product_id"].astype("int64"),
            "date_parsed": pd.PeriodIndex(keep["month"], freq="M").to_timestamp(),
            "openBalance": keep["opening_balance"].astype(float),
            "received": keep["received"].astype(float),
            "consumption": keep["consumption"].astype(float),
            "closeBalance": keep["closing_balance"].astype(float),
            "stockout": keep["stockout"].fillna(0).astype(int),
        }
    )

    registry = runtime.facilities[["hf_pk", "facility_type", "district"]]
    rows = rows.merge(registry, on="hf_pk", how="left")

    # A facility not in the registry (a genuinely new one) gets NaN from
    # that merge. If the upload supplied its own facility_type/district,
    # use them — the facility's real attributes beat a training-set average
    # standing in for them via the preprocessor's most-frequent imputer.
    for optional_field, panel_column in (("facility_type", "facility_type"), ("district", "district")):
        if optional_field in keep.columns:
            supplied = keep[optional_field].reset_index(drop=True)
            rows[panel_column] = rows[panel_column].fillna(supplied)

    product_constants = (
        runtime.panel[["productID", "normAvg", "normStd"]].drop_duplicates("productID")
    )
    return rows.merge(product_constants, on="productID", how="left")
