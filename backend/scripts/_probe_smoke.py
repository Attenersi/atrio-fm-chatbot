"""One-off: login as admin, POST full LLM profile probe with JSON body. Run from repo root or backend."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

from dotenv import load_dotenv

BASE = os.environ.get("PROBE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def main() -> int:
    here = Path(__file__).resolve().parent
    load_dotenv(here.parent / ".env")
    user = os.getenv("ADMIN_USERNAME", "admin")
    pw = os.getenv("ADMIN_PASSWORD", "admin")

    cj = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    def post(url: str, body: dict | None = None) -> tuple[int, str]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
            method="POST",
        )
        try:
            r = opener.open(req, timeout=120)
            return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def get(url: str) -> tuple[int, str]:
        req = urllib.request.Request(url, method="GET")
        try:
            r = opener.open(req, timeout=30)
            return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    code, body = post(f"{BASE}/api/auth/login", {"username": user, "password": pw})
    if code != 200:
        print("LOGIN_FAIL", code, body[:500])
        return 1

    code, body = get(f"{BASE}/api/admin/llm/profiles")
    if code != 200:
        print("LIST_PROFILES_FAIL", code, body[:500])
        return 1
    profiles = json.loads(body).get("profiles") or []
    if not profiles:
        print("NO_PROFILES (create one in admin UI first)")
        return 0

    pid = int(profiles[0]["id"])
    url = f"{BASE}/api/admin/llm/profiles/{pid}/probe"
    code, body = post(url, {"mode": "full"})
    if code != 200:
        print("PROBE_FAIL", code, body[:800])
        return 1
    print("PROBE_RAW_HEAD", body[:400].replace("\n", " "))
    out = json.loads(body)
    steps = out.get("steps")
    print("probe_ok keys:", sorted(out.keys()))
    print("steps_is_list:", isinstance(steps, list), "len:", len(steps) if isinstance(steps, list) else None)
    print("summary:", (out.get("summary") or "")[:200])
    if not isinstance(steps, list) or len(steps) == 0 or not isinstance(out.get("summary"), str):
        print("UNEXPECTED_SHAPE")
        return 1
    print("SMOKE_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
