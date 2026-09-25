"""Unpack Madad_Integrated_Data.zip into data/raw/, repeatably, on any machine.

Usage (from the repo root):
    python scripts/unpack_data.py
"""

import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = REPO_ROOT / "Madad_Integrated_Data.zip"
RAW_DIR = REPO_ROOT / "data" / "raw"

COMPRESSION_NAMES = {
    zipfile.ZIP_STORED: "stored",
    zipfile.ZIP_DEFLATED: "deflated",
    zipfile.ZIP_BZIP2: "bzip2",
    zipfile.ZIP_LZMA: "lzma",
}


def human_size(num_bytes):
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def check_for_split_archive():
    siblings = [
        p
        for p in ARCHIVE.parent.iterdir()
        if p.name != ARCHIVE.name
        and p.name.startswith(ARCHIVE.stem)
        and (p.suffix.lower() in (".z01", ".z02") or ".zip." in p.name.lower())
    ]
    if siblings:
        print(f"ERROR: found sibling archive parts, this looks like a split archive: {siblings}")
        sys.exit(1)


def safe_member_path(member_name, dest_dir):
    """Resolve a zip member path under dest_dir, rejecting anything that escapes it."""
    target = (dest_dir / member_name).resolve()
    dest_resolved = dest_dir.resolve()
    if dest_resolved != target and dest_resolved not in target.parents:
        raise ValueError(f"unsafe path in archive escapes extraction folder: {member_name!r}")
    return target


def collapse_single_top_level_folder(dest_dir):
    """If everything extracted into one subfolder, move its contents up and remove it."""
    entries = list(dest_dir.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        folder = entries[0]
        print(f"Collapsing single top-level folder: {folder.name}/")
        for child in folder.iterdir():
            child.rename(dest_dir / child.name)
        folder.rmdir()


def print_raw_dir_contents(dest_dir):
    print(f"\nFinal contents of {dest_dir}:")
    entries = sorted(p for p in dest_dir.iterdir() if p.name != ".gitkeep")
    if not entries:
        print("  (empty)")
        return
    for path in entries:
        if path.is_dir():
            print(f"  {path.name}/  (directory)")
        else:
            size = path.stat().st_size
            print(f"  {path.name}  {human_size(size)} ({size} bytes)  ext={path.suffix!r}")


def main():
    if not ARCHIVE.exists():
        print(f"ERROR: archive not found at {ARCHIVE}")
        sys.exit(1)

    check_for_split_archive()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(ARCHIVE) as zf:
            infos = zf.infolist()

            print(f"Archive: {ARCHIVE.name}")
            print(f"Entries: {len(infos)}\n")
            for info in infos:
                comp_name = COMPRESSION_NAMES.get(info.compress_type, f"unknown({info.compress_type})")
                kind = "dir" if info.is_dir() else "file"
                print(
                    f"  [{kind}] {info.filename!r}  "
                    f"uncompressed={human_size(info.file_size)} ({info.file_size} bytes)  "
                    f"compression={comp_name}"
                )

            # Validate every member path before extracting anything.
            for info in infos:
                safe_member_path(info.filename, RAW_DIR)

            print(f"\nExtracting into {RAW_DIR} ...")
            zf.extractall(RAW_DIR)

    except RuntimeError as e:
        # zipfile raises RuntimeError for password-protected members.
        print(f"ERROR: extraction failed (possibly password-protected): {e}")
        sys.exit(1)
    except NotImplementedError as e:
        print(f"ERROR: unsupported compression method: {e}")
        sys.exit(1)
    except zipfile.BadZipFile as e:
        print(f"ERROR: not a valid zip file: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    collapse_single_top_level_folder(RAW_DIR)
    print_raw_dir_contents(RAW_DIR)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
