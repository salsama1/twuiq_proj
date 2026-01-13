from __future__ import annotations

import os
import statistics
import time
from typing import Any, Dict, List, Optional, Tuple

import requests


BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT_SEC = float(os.getenv("BENCH_TIMEOUT_SEC", "120"))


def _pct(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    vs = sorted(values)
    if len(vs) == 1:
        return float(vs[0])
    k = (len(vs) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(vs) - 1)
    if f == c:
        return float(vs[f])
    d0 = vs[f] * (c - k)
    d1 = vs[c] * (k - f)
    return float(d0 + d1)


def _post(path: str, payload: Dict[str, Any]) -> Tuple[int, float, str]:
    url = f"{BASE_URL}{path}"
    t0 = time.perf_counter()
    r = requests.post(url, json=payload, timeout=TIMEOUT_SEC)
    ms = (time.perf_counter() - t0) * 1000.0
    return r.status_code, ms, r.text[:300]


def run_case(name: str, path: str, payload: Dict[str, Any], n: int) -> None:
    times: List[float] = []
    codes: Dict[int, int] = {}
    failures: int = 0

    # warmup
    for _ in range(2):
        try:
            _post(path, payload)
        except Exception:
            pass

    for _ in range(n):
        try:
            code, ms, _ = _post(path, payload)
            times.append(ms)
            codes[code] = codes.get(code, 0) + 1
            if code < 200 or code >= 300:
                failures += 1
        except Exception:
            failures += 1

    print(f"\n== {name} ==")
    print(f"path: {path}")
    print(f"n: {n}  failures: {failures}")
    print(f"status_counts: {dict(sorted(codes.items()))}")
    if times:
        print(
            "latency_ms: "
            f"p50={_pct(times,50):.1f}  p90={_pct(times,90):.1f}  p95={_pct(times,95):.1f}  "
            f"min={min(times):.1f}  max={max(times):.1f}  mean={statistics.mean(times):.1f}"
        )


def main() -> int:
    n = int(os.getenv("BENCH_N", "10"))

    # These hit the full stack through HTTP and reflect "real" demo latency.
    cases: List[Tuple[str, str, Dict[str, Any]]] = [
        (
            "RAG + LLM (query/rag)",
            "/query/rag",
            {"query": "Summarize gold occurrences in Riyadh and what patterns you see."},
        ),
        (
            "Workflow (offline summary)",
            "/agent/workflow",
            {"query": "Run QC summary and top commodities, then generate charts.", "max_steps": 10, "use_llm": False},
        ),
        (
            "Workflow (LLM summary)",
            "/agent/workflow",
            {"query": "Run QC summary and top commodities, then generate charts.", "max_steps": 10, "use_llm": True},
        ),
    ]

    print(f"BASE_URL={BASE_URL}")
    for name, path, payload in cases:
        run_case(name, path, payload, n=n)

    print("\nTip: If LLM is slow, set LLM_TIMEOUT_SEC higher or run workflow with use_llm=false.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

