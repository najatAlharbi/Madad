"""Upload a month of stock data: parse, map, validate, confirm.

Flow (matches the 4-step stepper in design/screens.md):
  POST /api/upload           file -> parsed preview + suggested mapping + validation
  POST /api/upload/confirm   mapping -> validated rows stored on the session
  POST /api/demo/load        load the bundled demo facility month instead
  GET  /api/upload/template  a blank CSV in the expected shape
"""

from __future__ import annotations

import io
import json
import logging

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile

from app.api.deps import require_session, runtime_dep
from app.core.config import DEMO_DIR
from app.core.runtime import Runtime
from app.core.session_store import Session, store
from app.ml.validate_input import (
    OPTIONAL_FIELDS,
    REQUIRED_FIELDS,
    apply_mapping,
    suggest_mapping,
    to_panel_rows,
    validate,
)

logger = logging.getLogger("madad.upload")

router = APIRouter(tags=["upload"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
PREVIEW_ROWS = 8


def _read_table(filename: str, raw: bytes) -> pd.DataFrame:
    """Parse an uploaded CSV or XLSX into a DataFrame."""
    name = (filename or "").lower()
    try:
        if name.endswith((".xlsx", ".xlsm", ".xls")):
            return pd.read_excel(io.BytesIO(raw))
        return pd.read_csv(io.BytesIO(raw))
    except Exception as exc:  # parser errors are user errors here, not bugs
        raise HTTPException(
            status_code=400,
            detail={"error": "unreadable_file", "message": f"Could not read {filename or 'the file'}: {exc}"},
        ) from exc


def _validated_payload(frame: pd.DataFrame, runtime: Runtime) -> dict:
    return validate(
        frame,
        known_facilities=set(runtime.facilities["hf_pk"].astype(int)),
        known_products=runtime.known_product_ids(),
        panel=runtime.panel,
        catalogue=runtime.product_names,
    )


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    session: Session = Depends(require_session),
    runtime: Runtime = Depends(runtime_dep),
) -> dict:
    """Parse a file and return a preview, a suggested mapping and the checks.

    Nothing is stored on the session yet — the user confirms the mapping
    first, because a wrong guess silently mis-forecasts.
    """
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error": "file_too_large", "message": f"Keep uploads under {MAX_UPLOAD_BYTES // 1024 // 1024} MB."},
        )

    table = _read_table(file.filename, raw)
    if table.empty:
        raise HTTPException(status_code=400, detail={"error": "empty_file", "message": "That file has no rows."})

    columns = [str(c) for c in table.columns]
    mapping = suggest_mapping(columns)

    # Validate against the suggestion so the user sees real checks immediately.
    resolved = {field: info["column"] for field, info in mapping.items() if info["column"]}
    provisional = _validated_payload(apply_mapping(table, resolved), runtime) if resolved else None

    session.upload_meta = {"filename": file.filename, "rows": len(table), "columns": columns}
    logger.info("upload parsed: %s (%d rows, %d columns)", file.filename, len(table), len(columns))

    return {
        "filename": file.filename,
        "row_count": len(table),
        "columns": columns,
        "required_fields": REQUIRED_FIELDS,
        "optional_fields": OPTIONAL_FIELDS,
        "suggested_mapping": mapping,
        "preview": table.head(PREVIEW_ROWS).astype(str).to_dict(orient="records"),
        "validation": provisional,
    }


@router.post("/upload/confirm")
async def confirm(
    file: UploadFile = File(...),
    mapping: str = Form(..., description='JSON object of canonical_field -> column name'),
    use_calculated_closing: bool = Form(False),
    session: Session = Depends(require_session),
    runtime: Runtime = Depends(runtime_dep),
) -> dict:
    """Apply a confirmed mapping and store the month on the session.

    Multipart rather than JSON because the file rides along: the client
    re-sends it with the mapping instead of the server holding a
    half-finished upload between two calls.
    """
    try:
        resolved_mapping = json.loads(mapping)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail={"error": "bad_mapping", "message": str(exc)}) from exc

    table = _read_table(file.filename, await file.read())
    frame = apply_mapping(table, resolved_mapping)

    if use_calculated_closing and {"opening_balance", "received", "consumption"} <= set(frame.columns):
        frame["closing_balance"] = frame["opening_balance"] + frame["received"] - frame["consumption"]

    report = _validated_payload(frame, runtime)
    if report["blocking"]:
        raise HTTPException(status_code=422, detail={"error": "validation_failed", "validation": report})

    rows = to_panel_rows(frame, report["drop_rows"], runtime)
    if rows.empty:
        raise HTTPException(status_code=422, detail={"error": "no_usable_rows", "validation": report})

    facility_id = int(rows["hf_pk"].iloc[0])
    store.reset_forecast(session)
    session.uploaded_df = rows
    session.facility_id = facility_id
    session.is_demo = False
    session.upload_meta = {
        "filename": file.filename,
        "month": report["month"],
        "rows": int(len(rows)),
        "skipped": len(report["drop_rows"]),
        "validation": report,
    }

    logger.info("upload confirmed: facility=%s month=%s rows=%d", facility_id, report["month"], len(rows))
    return {
        "facility_id": facility_id,
        "month": report["month"],
        "stored_rows": int(len(rows)),
        "skipped_rows": len(report["drop_rows"]),
        "validation": report,
        "is_demo": False,
    }


@router.post("/demo/load")
def load_demo(
    session: Session = Depends(require_session),
    runtime: Runtime = Depends(runtime_dep),
) -> dict:
    """Load the bundled demo facility-month into the session.

    Flagged ``is_demo`` all the way through so every screen can badge it —
    sample data is never presented as the user's own.
    """
    candidates = sorted(DEMO_DIR.glob("facility_*_*.csv")) if DEMO_DIR.exists() else []
    if not candidates:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "demo_unavailable",
                "message": "No demo file found. Run `python scripts/export_artifacts.py`.",
            },
        )

    path = candidates[0]
    table = pd.read_csv(path)

    # The demo file is cut from the panel, so its headers are already canonical
    # in meaning; map them through the same path a user's file takes.
    mapping = {field: info["column"] for field, info in suggest_mapping([str(c) for c in table.columns]).items() if info["column"]}
    frame = apply_mapping(table, mapping)
    report = _validated_payload(frame, runtime)
    rows = to_panel_rows(frame, report["drop_rows"], runtime)

    if rows.empty:
        raise HTTPException(status_code=500, detail={"error": "demo_invalid", "validation": report})

    facility_id = int(rows["hf_pk"].iloc[0])
    store.reset_forecast(session)
    session.uploaded_df = rows
    session.facility_id = facility_id
    session.is_demo = True
    session.upload_meta = {
        "filename": path.name,
        "month": report["month"],
        "rows": int(len(rows)),
        "skipped": len(report["drop_rows"]),
        "validation": report,
        "is_demo": True,
    }

    logger.info("demo loaded: %s facility=%s month=%s", path.name, facility_id, report["month"])
    return {
        "facility_id": facility_id,
        "month": report["month"],
        "stored_rows": int(len(rows)),
        "skipped_rows": len(report["drop_rows"]),
        "validation": report,
        "is_demo": True,
        "source_file": path.name,
    }


@router.get("/products")
def products(runtime: Runtime = Depends(runtime_dep)) -> dict:
    """The tracked supplies, code and name.

    The upload screen shows this so a manager can see exactly which
    supplies Madad understands, and copy the spelling it expects.
    """
    return {
        "count": len(runtime.product_names),
        "products": [
            {"product_id": int(product_id), "name": name}
            for product_id, name in sorted(runtime.product_names.items())
        ],
    }


@router.get("/upload/template")
def template(runtime: Runtime = Depends(runtime_dep)) -> Response:
    """A CSV template with one pre-filled row per tracked supply.

    Only the six fields a manager actually has to supply. Opening balance,
    stockout and the internal product code are all worked out server-side
    and are deliberately absent: fewer columns to fill in is fewer chances
    to get one wrong. Pre-listing the supply names also means the spelling
    always matches the catalogue.
    """
    lines = [",".join(REQUIRED_FIELDS)]
    for name in sorted(runtime.product_names.values()):
        lines.append(f',"{name}",,,,')
    body = "\n".join(lines) + "\n"
    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="madad_upload_template.csv"'},
    )
