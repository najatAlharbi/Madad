"""Profile the files in data/raw/ without assuming their format.

Detects the real file type from magic bytes, loads each file with the
matching pandas reader, records the exact reader call in
docs/data_profile.md (so prepare_data.py can reuse it), and runs a deep
profile of the table that holds the monthly facility-product records.

Usage (from the repo root):
    python scripts/profile_data.py
"""

import csv
import sys
import warnings
import zipfile
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
DOCS_DIR = REPO_ROOT / "docs"
PROFILE_MD = DOCS_DIR / "data_profile.md"

# Columns expected on the monthly facility-product table (from notebook 07).
MONTHLY_TABLE_KEY_COLUMNS = {"hf_pk", "productID", "date_parsed", "consumption"}


def sniff_encoding(sample_bytes):
    if sample_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            sample_bytes.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"  # never fails, last resort


def sniff_delimiter(path, encoding):
    with open(path, "r", encoding=encoding, errors="replace") as f:
        sample = f.read(65536)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        return ","


def detect_zip_subtype(path):
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
    except zipfile.BadZipFile:
        return "zip (unreadable)"
    if any(n.startswith("xl/") for n in names):
        return "xlsx"
    if any(n.startswith("word/") for n in names):
        return "docx"
    if any(n.startswith("ppt/") for n in names):
        return "pptx"
    return "zip"


def detect_format(path):
    with open(path, "rb") as f:
        head = f.read(16)

    if head.startswith(b"PAR1"):
        return "parquet"
    if head.startswith(b"SQLite format 3\x00"):
        return "sqlite"
    if head.startswith(b"\x1f\x8b"):
        return "gzip"
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        return detect_zip_subtype(path)

    # Not a known binary magic: treat as text and narrow down further.
    with open(path, "rb") as f:
        sample = f.read(65536)
    encoding = sniff_encoding(sample)
    text_sample = sample.decode(encoding, errors="replace").lstrip()
    if text_sample.startswith("{") or text_sample.startswith("["):
        return "json"
    return "csv"


def profile_generic(path, fmt):
    """Load a file with the reader matching its detected format, return (df_or_dict, reader_info)."""
    if fmt == "parquet":
        df = pd.read_parquet(path)
        return df, {"reader": "pandas.read_parquet", "args": {}}

    if fmt == "xlsx":
        xl = pd.ExcelFile(path)
        print(f"  Sheet names: {xl.sheet_names}")
        df = pd.read_excel(path, sheet_name=xl.sheet_names[0])
        return df, {
            "reader": "pandas.read_excel",
            "args": {"sheet_name": xl.sheet_names[0]},
            "all_sheets": xl.sheet_names,
        }

    if fmt == "json":
        with open(path, "rb") as f:
            sample = f.read(65536)
        encoding = sniff_encoding(sample)
        try:
            df = pd.read_json(path, encoding=encoding, lines=False)
            lines = False
        except ValueError:
            df = pd.read_json(path, encoding=encoding, lines=True)
            lines = True
        return df, {"reader": "pandas.read_json", "args": {"encoding": encoding, "lines": lines}}

    if fmt == "csv":
        with open(path, "rb") as f:
            sample = f.read(65536)
        encoding = sniff_encoding(sample)
        delimiter = sniff_delimiter(path, encoding)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            df = pd.read_csv(path, encoding=encoding, sep=delimiter, low_memory=False)
            needs_low_memory = any(
                issubclass(w.category, pd.errors.DtypeWarning) for w in caught
            )
        return df, {
            "reader": "pandas.read_csv",
            "args": {"encoding": encoding, "sep": delimiter, "low_memory": False},
            "dtype_warning_without_low_memory": needs_low_memory,
        }

    raise ValueError(f"unsupported/unrecognized format for profiling: {fmt}")


def deep_profile_monthly_table(df, out):
    out.append("\n### Deep profile: monthly facility-product table\n")

    out.append(f"- Row count: {len(df):,}")
    out.append(f"- Column count: {df.shape[1]}")
    out.append("\n**Columns and dtypes:**\n")
    out.append("| column | dtype |")
    out.append("|---|---|")
    for col, dtype in df.dtypes.items():
        out.append(f"| {col} | {dtype} |")

    out.append("\n**Head (10 rows):**\n")
    out.append("```")
    out.append(df.head(10).to_string())
    out.append("```")

    out.append("\n**Per-column profile:**\n")
    out.append("| column | nulls | distinct | min | max |")
    out.append("|---|---|---|---|---|")
    for col in df.columns:
        series = df[col]
        nulls = int(series.isna().sum())
        distinct = int(series.nunique(dropna=True))
        if pd.api.types.is_numeric_dtype(series):
            col_min = series.min()
            col_max = series.max()
        else:
            col_min = ""
            col_max = ""
        out.append(f"| {col} | {nulls} | {distinct} | {col_min} | {col_max} |")

    # Date column.
    date_col = "date_parsed" if "date_parsed" in df.columns else "date"
    parsed_dates = pd.to_datetime(df[date_col], errors="coerce")
    out.append(f"\n**Date column (`{date_col}`):**\n")
    out.append(f"- Parsed range: {parsed_dates.min()} to {parsed_dates.max()}")
    out.append(f"- Unparseable dates: {int(parsed_dates.isna().sum())}")

    key_cols = ["hf_pk", "productID"]
    if all(c in df.columns for c in key_cols):
        rows_per_key = df.groupby(key_cols).size()
        months_per_key = df.groupby(key_cols)[date_col].apply(
            lambda s: pd.to_datetime(s, errors="coerce").nunique()
        )
        one_row_per_month = (rows_per_key == months_per_key).all()
        out.append(
            f"- One row per facility-product-month: "
            f"{'yes' if one_row_per_month else 'no'}"
        )

        # Gap count: for each facility-product series, count missing months
        # between its first and last observed month (monthly cadence).
        gap_count = 0
        for _, group in df.groupby(key_cols):
            months = (
                pd.to_datetime(group[date_col], errors="coerce")
                .dropna()
                .dt.to_period("M")
                .drop_duplicates()
                .sort_values()
            )
            if len(months) > 1:
                full_range = pd.period_range(months.min(), months.max(), freq="M")
                gap_count += len(full_range) - len(months)
        out.append(f"- Total missing months across all facility-product series (gaps): {gap_count}")

        out.append(f"- Distinct facilities: {df['hf_pk'].nunique()}")
        out.append(f"- Distinct products: {df['productID'].nunique()}")
        out.append("\n**Rows per facility-product (describe):**\n")
        out.append("```")
        out.append(rows_per_key.describe().to_string())
        out.append("```")

        dup_key_cols = key_cols + [date_col]
        dup_count = int(df.duplicated(subset=dup_key_cols).sum())
        out.append(f"\n- Duplicate (facility, product, month) rows: {dup_count}")

    balance_cols = ["openBalance", "received", "consumption", "closeBalance"]
    if all(c in df.columns for c in balance_cols):
        out.append("\n**Balance columns:**\n")
        for col in balance_cols:
            neg = int((df[col] < 0).sum())
            out.append(f"- Negative values in `{col}`: {neg}")

        expected_close = df["openBalance"] + df["received"] - df["consumption"]
        mismatch = int((df["closeBalance"] != expected_close).sum())
        out.append(
            f"- Rows where closeBalance != openBalance + received - consumption: {mismatch}"
        )

        zero_consumption_share = float((df["consumption"] == 0).mean())
        out.append(f"- Share of zero consumption: {zero_consumption_share:.4%}")


def main():
    files = sorted(p for p in RAW_DIR.iterdir() if p.is_file() and p.name != ".gitkeep")
    if not files:
        print(f"No files found in {RAW_DIR}. Run scripts/unpack_data.py first.")
        sys.exit(1)

    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    md_lines = ["# Data Profile\n"]
    md_lines.append(f"Profiled {len(files)} file(s) in `data/raw/`.\n")

    monthly_table_df = None

    for path in files:
        fmt = detect_format(path)
        print(f"\n=== {path.name} ===")
        print(f"Detected format: {fmt}")

        df, reader_info = profile_generic(path, fmt)
        print(f"Reader: {reader_info['reader']}({reader_info['args']})")
        print(f"Shape: {df.shape}")

        md_lines.append(f"## `{path.name}`\n")
        md_lines.append(f"- Detected format: `{fmt}`")
        md_lines.append(f"- Reader: `{reader_info['reader']}`")
        md_lines.append(f"- Reader args: `{reader_info['args']}`")
        if "all_sheets" in reader_info:
            md_lines.append(f"- Sheet names: {reader_info['all_sheets']}")
        if "dtype_warning_without_low_memory" in reader_info:
            md_lines.append(
                f"- Needs `low_memory=False` to avoid a DtypeWarning: "
                f"{reader_info['dtype_warning_without_low_memory']}"
            )
        md_lines.append(f"- Shape: {df.shape[0]:,} rows x {df.shape[1]} columns")
        md_lines.append(f"- Columns: {list(df.columns)}\n")

        if MONTHLY_TABLE_KEY_COLUMNS.issubset(df.columns):
            monthly_table_df = df

    if len(files) > 1:
        md_lines.append("## How the files relate\n")
        md_lines.append(
            "Only one candidate relation check is implemented here (shared columns); "
            "review manually if more files are added.\n"
        )
        col_sets = {p.name: set(pd.read_csv(p, nrows=0).columns) if detect_format(p) == "csv" else None for p in files}
        for a in files:
            for b in files:
                if a.name >= b.name:
                    continue
                if col_sets.get(a.name) and col_sets.get(b.name):
                    shared = col_sets[a.name] & col_sets[b.name]
                    md_lines.append(f"- `{a.name}` & `{b.name}` share columns: {sorted(shared) or 'none'}")
    else:
        print("\nOnly one file present in data/raw/ — no cross-file relations to check.")

    if monthly_table_df is not None:
        print("\nRunning deep profile on the monthly facility-product table...")
        deep_profile_monthly_table(monthly_table_df, md_lines)
    else:
        print("\nNo file matched the expected monthly facility-product columns "
              f"({sorted(MONTHLY_TABLE_KEY_COLUMNS)}); skipping deep profile.")

    PROFILE_MD.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"\nWrote {PROFILE_MD}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
