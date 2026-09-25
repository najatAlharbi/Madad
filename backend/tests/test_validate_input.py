"""Upload mapping and validation rules."""

import pandas as pd
import pytest

from app.ml.validate_input import (
    REQUIRED_FIELDS,
    apply_mapping,
    derive_optional_fields,
    resolve_product_names,
    suggest_mapping,
    validate,
)

KNOWN_FACILITIES = {780, 801}
KNOWN_PRODUCTS = {34, 39, 46, 50}

CATALOGUE = {
    34: "Folic Acid 5mg, Tab",
    39: "Oral Rehydration Salts (ORS), Sachet",
    46: "Paracetamol (Acetaminophen) 250mg, Dispersible, Tab",
    50: "Paracetamol (Acetaminophen) 500mg, Tab",
}


def good_frame():
    """The six fields a manager actually supplies - nothing more."""
    return pd.DataFrame(
        {
            "facility_id": [780, 780],
            "product_name": ["Folic Acid 5mg, Tab", "Oral Rehydration Salts (ORS), Sachet"],
            "month": ["2023-03", "2023-03"],
            "received": [0.0, 20.0],
            "consumption": [60.0, 50.0],
            "closing_balance": [40.0, 50.0],
        }
    )


def run(frame):
    return validate(frame, KNOWN_FACILITIES, KNOWN_PRODUCTS, catalogue=CATALOGUE)


def level_of(report, check_id):
    return next(c["level"] for c in report["checks"] if c["id"] == check_id)


# --- mapping ---------------------------------------------------------


def test_suggest_mapping_matches_exact_names():
    suggestions = suggest_mapping(REQUIRED_FIELDS)
    for field in REQUIRED_FIELDS:
        assert suggestions[field]["column"] == field
        assert suggestions[field]["confidence"] == "high"


def test_required_set_is_only_what_a_manager_can_know():
    """Opening balance, stockout and the internal code must not be required."""
    assert REQUIRED_FIELDS == [
        "facility_id", "product_name", "month",
        "received", "consumption", "closing_balance",
    ]
    for derived in ("opening_balance", "stockout", "product_id"):
        assert derived not in REQUIRED_FIELDS


def test_suggest_mapping_handles_panel_style_headers():
    """A file exported from this app's own panel should map itself."""
    suggestions = suggest_mapping(["hf_pk", "productID", "date", "openBalance", "received", "consumption", "closeBalance", "stockout"])
    assert suggestions["facility_id"]["column"] == "hf_pk"
    assert suggestions["product_id"]["column"] == "productID"
    assert suggestions["closing_balance"]["column"] == "closeBalance"


def test_suggest_mapping_reports_unmatched_fields():
    suggestions = suggest_mapping(["something", "unrelated"])
    assert suggestions["consumption"]["column"] is None
    assert suggestions["consumption"]["confidence"] == "none"


def test_apply_mapping_normalises_month_and_types():
    raw = pd.DataFrame({"fac": ["780"], "prod": ["34"], "when": ["2023-03-15"], "used": ["60"]})
    frame = apply_mapping(raw, {"facility_id": "fac", "product_id": "prod", "month": "when", "consumption": "used"})
    assert frame["month"].iloc[0] == "2023-03"
    assert frame["facility_id"].iloc[0] == 780
    assert frame["consumption"].iloc[0] == 60


# --- validation ------------------------------------------------------


def test_clean_upload_passes_everything():
    report = run(good_frame())
    assert report["blocking"] is False
    assert report["usable_rows"] == 2
    assert report["month"] == "2023-03"
    assert all(check["level"] == "pass" for check in report["checks"])


def test_missing_required_column_blocks():
    frame = good_frame().drop(columns=["consumption"])
    report = run(frame)
    assert report["blocking"] is True
    assert level_of(report, "required_columns") == "block"


def test_unknown_product_drops_that_row_only():
    frame = good_frame()
    frame.loc[1, "product_name"] = "Aspirin 300mg"
    report = run(frame)
    assert level_of(report, "product_name_match") == "block"
    assert report["drop_rows"] == [2]
    assert report["usable_rows"] == 1
    # One bad row must not block the whole file.
    assert report["blocking"] is False


def test_opening_balance_and_stockout_are_derived():
    report = run(good_frame())
    assert set(report["derived_fields"]) == {"opening_balance", "stockout"}
    assert level_of(report, "derived_fields") == "pass"


def test_derivation_follows_the_balance_identity():
    frame, derived = derive_optional_fields(good_frame())
    # closing 40 = opening + received 0 - consumption 60  ->  opening 100
    assert frame["opening_balance"].iloc[0] == 100.0
    assert "opening_balance" in derived


def test_stockout_is_derived_from_an_empty_closing_balance():
    frame = good_frame()
    frame.loc[0, "closing_balance"] = 0.0
    derived_frame, _ = derive_optional_fields(frame)
    assert derived_frame["stockout"].tolist() == [1, 0]


def test_supplied_opening_balance_is_respected_and_still_checked():
    frame = good_frame()
    frame["opening_balance"] = [999.0, 80.0]   # first row does not reconcile
    report = run(frame)
    assert "opening_balance" not in report["derived_fields"]
    assert level_of(report, "balance_identity") == "warning"


def test_unknown_facility_is_a_warning_not_a_block():
    frame = good_frame()
    frame["facility_id"] = 999999
    report = run(frame)
    assert level_of(report, "facility_known") == "warning"
    assert report["blocking"] is False


def test_balance_mismatch_warns_beyond_tolerance():
    frame = good_frame()
    frame["opening_balance"] = [100.0, 80.0]
    frame.loc[0, "closing_balance"] = 999.0
    assert level_of(run(frame), "balance_identity") == "warning"


def test_balance_within_one_unit_still_passes():
    """Tolerance is 1 unit, per the brief."""
    frame = good_frame()
    frame["opening_balance"] = [100.0, 80.0]
    frame.loc[0, "closing_balance"] = 40.5
    assert level_of(run(frame), "balance_identity") == "pass"


def test_negative_quantity_drops_the_row():
    frame = good_frame()
    frame.loc[0, "received"] = -5.0
    report = run(frame)
    assert level_of(report, "no_negatives") == "block"
    assert 1 in report["drop_rows"]


def test_duplicate_rows_keep_the_first():
    frame = pd.concat([good_frame(), good_frame().head(1)], ignore_index=True)
    report = run(frame)
    assert level_of(report, "no_duplicates") == "block"
    assert report["drop_rows"] == [3]


def test_unparseable_month_is_flagged():
    frame = good_frame()
    frame["month"] = ["not-a-date", "also-bad"]
    report = run(frame)
    assert level_of(report, "month_parse") == "block"
    assert report["usable_rows"] == 0
    assert report["blocking"] is True


def test_multiple_months_warns_and_takes_the_latest():
    frame = good_frame()
    frame.loc[1, "month"] = "2023-04"
    report = run(frame)
    assert level_of(report, "single_month") == "warning"
    assert report["month"] == "2023-04"


@pytest.mark.parametrize("check_id", ["required_columns", "facility_known", "no_negatives", "no_duplicates"])
def test_every_briefed_check_is_reported(check_id):
    report = run(good_frame())
    assert any(check["id"] == check_id for check in report["checks"])


# --- product names ---------------------------------------------------
#
# A warehouse manager's spreadsheet identifies supplies by name, not by the
# dataset's internal code, so a file with names and no codes must work.

def names_frame(names):
    return pd.DataFrame(
        {
            "facility_id": [780] * len(names),
            "product_name": names,
            "month": ["2023-03"] * len(names),
            "received": [0.0] * len(names),
            "consumption": [40.0] * len(names),
            "closing_balance": [60.0] * len(names),
        }
    )


def test_product_name_is_suggested_before_product_id():
    """A column literally called 'Item Description' must not be swallowed
    by product_id's looser synonyms."""
    suggestions = suggest_mapping(["Site Code", "Item Code", "Item Description", "month"])
    assert suggestions["product_name"]["column"] == "Item Description"
    assert suggestions["product_id"]["column"] == "Item Code"


def test_exact_name_resolves_to_its_code():
    frame, unresolved, conflicting = resolve_product_names(
        names_frame(["Paracetamol (Acetaminophen) 500mg, Tab"]), CATALOGUE
    )
    assert frame["product_id"].iloc[0] == 50
    assert not unresolved and not conflicting


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("Folic Acid 5mg", 34),                       # partial — no ", Tab"
        ("FOLIC ACID 5MG, TAB", 34),                  # shouting
        ("folic-acid 5mg tab", 34),                   # different punctuation
        ("Oral Rehydration Salts (ORS) Sachet", 39),  # missing comma
    ],
)
def test_name_matching_tolerates_how_people_actually_type(written, expected):
    frame, unresolved, _ = resolve_product_names(names_frame([written]), CATALOGUE)
    assert frame["product_id"].iloc[0] == expected, written
    assert not unresolved


def test_unknown_name_is_left_unresolved_not_guessed():
    frame, unresolved, _ = resolve_product_names(names_frame(["Aspirin 300mg"]), CATALOGUE)
    assert pd.isna(frame["product_id"].iloc[0])
    assert unresolved == [1]


def test_names_only_upload_passes_validation():
    """No product_id column at all — the file must still be usable."""
    frame = names_frame(["Folic Acid 5mg, Tab", "Oral Rehydration Salts (ORS), Sachet"])
    report = validate(frame, KNOWN_FACILITIES, set(CATALOGUE), catalogue=CATALOGUE)
    assert report["blocking"] is False
    assert report["usable_rows"] == 2
    assert level_of(report, "product_name_match") == "pass"


def test_unrecognised_name_blocks_only_its_own_row():
    frame = names_frame(["Folic Acid 5mg, Tab", "Aspirin 300mg"])
    report = validate(frame, KNOWN_FACILITIES, set(CATALOGUE), catalogue=CATALOGUE)
    assert level_of(report, "product_name_match") == "block"
    assert report["drop_rows"] == [2]
    assert report["usable_rows"] == 1
    # The same row must not also be reported as an unknown *code*.
    assert not any(c["id"] == "product_known" for c in report["checks"])


def test_name_and_code_disagreement_warns_and_keeps_the_code():
    frame = names_frame(["Folic Acid 5mg, Tab"])
    frame["product_id"] = [50]  # says paracetamol, named folic acid
    report = validate(frame, KNOWN_FACILITIES, set(CATALOGUE), catalogue=CATALOGUE)
    assert level_of(report, "product_name_match") == "warning"
    assert report["usable_rows"] == 1
