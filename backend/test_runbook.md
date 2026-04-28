# RAG Test Runbook

## Known terminal issues observed

1. `HTTP 500` wrapping upstream `429 Too Many Requests` from NVIDIA NIM.
2. Request timeouts on `/api/chat` during long suites.
3. Backend autoreload (`--reload`) interrupts long test runs while files are edited.
4. SMTP auth errors (`535`) spam logs when `.env` has placeholder or invalid app password.

## Stable test procedure

1. Start backend once and avoid edits during run:
   - `venv\Scripts\python.exe -m app.main`
2. Keep frontend running separately (`npm run dev`) for manual checks.
3. Run tests with conservative limits (defaults in `test_rag.py` are tuned for slow NVIDIA):
   - `--sleep-between 15` (default)
   - `--max-retries 3`
   - `--retry-wait 10`
   - `--timeout 240` (default; increase further if many `request_error=timed out`)
4. If many timeouts remain, wait 60–120s cool-down, then rerun only `*_failed_api_error_case_ids.txt` with the same or higher `--timeout` / `--sleep-between`.
5. Ignore SMTP noise for RAG evaluation; it does not block `/api/chat`.

## Suggested command sequence

1. Full run:
   - `python -u test_rag.py --cases-file atrio_test_cases.json --output test_results_full.json`
2. Rerun failures (after a full run, the runner writes `test_results_full_failed_all_case_ids.txt` next to `--output`; use that path or any ID list you saved):
   - `python -u test_rag.py --cases-file atrio_test_cases.json --case-ids-file test_results_full_failed_all_case_ids.txt --compare-with test_results_full.json --output test_results_rerun.json`

## Output artifacts

Keep a single canonical report if you prefer: **`test_results_full.json`** (per-case rows, `summary`, optional `diff`). The runner also writes companion `*_failed_*_case_ids.txt` files beside the same basename; they are optional and can be deleted—they regenerate on the next run. Rerun JSON (e.g. `test_results_rerun.json`) is optional and only needed while comparing subsets.
