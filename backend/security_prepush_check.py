from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EXCLUDE_DIRS = {".git", "backend/venv", "frontend/node_modules", "backend/chroma_db"}
TEXT_EXTS = {".py", ".md", ".txt", ".json", ".jsonl", ".csv", ".env", ".example", ".yml", ".yaml", ".ts", ".tsx", ".js"}
SECRET_PATTERNS = [
    re.compile(r"nvapi-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"),
    re.compile(r"-----BEGIN (RSA|EC|OPENSSH|PRIVATE) KEY-----"),
]
BLOCKED_PATH_PATTERNS = [
    "backend/.env",
    "backend/tickets.db",
    "backend/chroma_db/",
    "backend/tests/results/",
    "backend/data/fine_tuning_v1_candidates.jsonl",
    "backend/data/fine_tuning_v1_train.jsonl",
    "backend/data/fine_tuning_v1_review.csv",
]


def _is_excluded(path: Path) -> bool:
    rel = path.as_posix()
    return any(rel.startswith(prefix) for prefix in EXCLUDE_DIRS)


def _iter_text_files() -> list[Path]:
    out: list[Path] = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT)
        if _is_excluded(rel):
            continue
        if p.suffix.lower() in TEXT_EXTS:
            out.append(p)
    return out


def _scan_secrets() -> list[str]:
    issues: list[str] = []
    for path in _iter_text_files():
        rel = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                if "REPLACE_WITH_" in text:
                    # Common placeholder in .env.example; not a real secret.
                    continue
                issues.append(f"secret-like pattern in {rel} ({pattern.pattern})")
                break
    return issues


def _git_staged_files() -> list[str] | None:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only"],
            cwd=ROOT,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return [line.strip() for line in out.splitlines() if line.strip()]
    except Exception:
        return None


def _check_staged_paths(staged: list[str]) -> list[str]:
    issues: list[str] = []
    for rel in staged:
        norm = rel.replace("\\", "/")
        for blocked in BLOCKED_PATH_PATTERNS:
            if blocked.endswith("/"):
                if norm.startswith(blocked):
                    issues.append(f"blocked staged path: {norm}")
            elif norm == blocked:
                issues.append(f"blocked staged path: {norm}")
    return issues


def main() -> int:
    print("Running pre-push security check...")
    issues: list[str] = []

    issues.extend(_scan_secrets())

    staged = _git_staged_files()
    if staged is None:
        print("Note: git repo not detected, staged-file policy check skipped.")
    else:
        issues.extend(_check_staged_paths(staged))

    if issues:
        print("\nFAIL: Security check found issues:")
        for i in issues:
            print(f"- {i}")
        return 1

    print("PASS: No obvious secrets or blocked staged paths found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
