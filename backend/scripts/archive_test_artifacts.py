from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SUITES_DIR = ROOT / "tests" / "suites"
RESULTS_DIR = ROOT / "tests" / "results"
ARCHIVE_DIR = ROOT / "tests" / "archive"
ARCHIVE_SUITES = ARCHIVE_DIR / "suites"
ARCHIVE_RESULTS = ARCHIVE_DIR / "results"


def _is_dated_name(path: Path) -> bool:
    # Current historical format: "DD.MM.YYYY, description.ext"
    name = path.name
    if "," not in name:
        return False
    prefix = name.split(",", 1)[0].strip()
    parts = prefix.split(".")
    if len(parts) != 3:
        return False
    return all(part.isdigit() for part in parts)


def _move_files(src_dir: Path, dst_dir: Path) -> int:
    moved = 0
    dst_dir.mkdir(parents=True, exist_ok=True)
    for path in src_dir.iterdir():
        if not path.is_file():
            continue
        if not _is_dated_name(path):
            continue
        target = dst_dir / path.name
        if target.exists():
            continue
        shutil.move(str(path), str(target))
        moved += 1
    return moved


def main() -> int:
    moved_suites = _move_files(SUITES_DIR, ARCHIVE_SUITES)
    moved_results = _move_files(RESULTS_DIR, ARCHIVE_RESULTS)
    print(f"moved suites: {moved_suites}")
    print(f"moved results: {moved_results}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

