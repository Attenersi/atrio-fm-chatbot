from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TESTS_DIR = ROOT / "tests"
RESULTS_DIR = TESTS_DIR / "results"
SUITES_DIR = TESTS_DIR / "suites"


def _date_label(path: Path) -> str:
    ts = path.stat().st_mtime
    return __import__("datetime").datetime.fromtimestamp(ts).strftime("%d.%m.%Y")


def _safe_text(value: str) -> str:
    value = re.sub(r'[\\/:*?"<>|]+', " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or "test file"


def _result_description(name: str) -> str:
    stem = Path(name).stem
    if stem.startswith("test_results_"):
        stem = stem[len("test_results_") :]
    stem = stem.replace("_failed_all_case_ids", ", failed all case ids")
    stem = stem.replace("_failed_api_ok_case_ids", ", failed api ok case ids")
    stem = stem.replace("_failed_api_error_case_ids", ", failed api error case ids")
    stem = stem.replace("_", " ")
    return _safe_text(stem)


def _suite_description(name: str) -> str:
    stem = Path(name).stem
    stem = stem.replace("_", " ")
    return _safe_text(stem)


def _next_free_path(directory: Path, filename: str) -> Path:
    base = directory / filename
    if not base.exists():
        return base
    stem = base.stem
    suffix = base.suffix
    i = 2
    while True:
        candidate = directory / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def _move(src: Path, dst_dir: Path, description: str) -> None:
    date = _date_label(src)
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst_name = f"{date}, {description}{src.suffix}"
    dst = _next_free_path(dst_dir, dst_name)
    src.rename(dst)
    print(f"moved: {src.name} -> {dst.relative_to(ROOT)}")


def main() -> int:
    candidates = [p for p in ROOT.iterdir() if p.is_file()]
    for path in candidates:
        name = path.name
        if name in {"test_rag.py", "organize_test_files.py"}:
            continue
        if name.startswith("test_results_") and path.suffix in {".json", ".txt"}:
            _move(path, RESULTS_DIR, _result_description(name))
            continue
        if re.match(r".*_failed_.*case_ids\.txt$", name):
            _move(path, RESULTS_DIR, _result_description(name))
            continue
        if name.endswith("_cases.json") or name in {
            "atrio_test_cases.json",
            "atrio_boundary_tests.json",
            "new_batches_all_cases.json",
            "weird_top10_ids.txt",
        }:
            _move(path, SUITES_DIR, _suite_description(name))
            continue
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
