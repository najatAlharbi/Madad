from pathlib import Path

from app.core.config import (
    MODELS_DIR,
    NOTEBOOKS_DIR,
    PANEL_PARQUET,
    RAW_DATA,
    RAW_FORMAT,
    REPO_ROOT,
    REPORTS_DIR,
)


def test_paths_are_absolute_and_under_repo_root():
    for path in (RAW_DATA, PANEL_PARQUET, MODELS_DIR, REPORTS_DIR, NOTEBOOKS_DIR):
        assert isinstance(path, Path)
        assert path.is_absolute()
        assert REPO_ROOT in path.parents


def test_raw_format_is_set():
    assert isinstance(RAW_FORMAT, str)
    assert RAW_FORMAT
