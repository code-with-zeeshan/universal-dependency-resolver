#!/usr/bin/env python3
"""Verify API endpoints are reachable (stdlib only, no external deps)."""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from typing import Dict, Any

BASE_URL = os.getenv("CHECK_URL", "http://localhost:8000/api/v1")


def check_endpoint(path: str, method: str = "GET") -> Dict[str, Any]:
    url = f"{BASE_URL}{path}"
    result = {"path": path, "success": False, "status": None, "error": None}
    try:
        req = urllib.request.Request(url, method=method)
        start = time.time()
        with urllib.request.urlopen(req, timeout=10) as resp:
            result["status"] = resp.status
            result["latency"] = round(time.time() - start, 3)
            body = resp.read().decode()
            json.loads(body)  # ensure valid JSON
        result["success"] = True
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        result["error"] = str(e)
    return result


def main():
    endpoints = ["/health", "/system/info", "/packages/export-formats", "/packages/search?q=numpy"]
    failures = 0
    for ep in endpoints:
        r = check_endpoint(ep)
        status = "PASS" if r["success"] else "FAIL"
        detail = f" ({r['status']})" if r["success"] else f" — {r['error']}"
        print(f"  [{status}] {ep}{detail}")
        if not r["success"]:
            failures += 1

    print(f"\n{len(endpoints) - failures}/{len(endpoints)} endpoints passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
