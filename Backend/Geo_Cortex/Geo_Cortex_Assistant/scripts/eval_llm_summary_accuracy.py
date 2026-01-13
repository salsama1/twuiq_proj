from __future__ import annotations

import os
import statistics
import time
from typing import Any, Dict, List, Tuple

import requests


BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT_SEC = float(os.getenv("EVAL_TIMEOUT_SEC", "120"))


CASES: List[Tuple[str, Dict[str, Any]]] = [
    (
        "qc+commodities+charts",
        {"query": "Run QC summary and top commodities, then generate charts.", "max_steps": 10, "use_llm": True},
    ),
    (
        "regions+commodities",
        {"query": "Give me counts by region and top commodities, and summarize.", "max_steps": 10, "use_llm": True},
    ),
    (
        "heatmap",
        {"query": "Generate a density/heatmap view and summarize what it means.", "max_steps": 10, "use_llm": True},
    ),
]


def _post_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.post(f"{BASE_URL}/agent/workflow", json=payload, timeout=TIMEOUT_SEC)
    r.raise_for_status()
    return r.json()


def main() -> int:
    n = int(os.getenv("EVAL_N", "10"))

    llm_ok = 0
    llm_total = 0
    sys_ok = 0
    sys_total = 0
    latencies: List[float] = []

    print(f"BASE_URL={BASE_URL}  EVAL_N={n}")

    for name, payload in CASES:
        for i in range(n):
            t0 = time.perf_counter()
            j = _post_workflow(payload)
            ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(ms)

            artifacts = j.get("artifacts") or {}
            source = artifacts.get("summary_source")
            validated = bool(artifacts.get("summary_validated"))

            sys_total += 1
            if validated:
                sys_ok += 1

            # LLM pass rate: only count cases where summary_source is "llm"
            if source == "llm":
                llm_total += 1
                if validated:
                    llm_ok += 1

        print(f"- ran case: {name}")

    sys_acc = (sys_ok / sys_total) if sys_total else 0.0
    llm_pass = (llm_ok / llm_total) if llm_total else 0.0

    print("\n== Summary accuracy results ==")
    print(f"system_validated_rate: {sys_acc:.3f} ({sys_ok}/{sys_total})")
    print(f"llm_validated_rate (when LLM used): {llm_pass:.3f} ({llm_ok}/{llm_total})")
    if latencies:
        print(
            "latency_ms: "
            f"p50={statistics.median(latencies):.1f}  max={max(latencies):.1f}  mean={statistics.mean(latencies):.1f}"
        )

    print("\nNotes:")
    print("- system_validated_rate includes deterministic fallback summaries when the LLM is slow or violates rules.")
    print("- llm_validated_rate measures how often the LLM output passed validation when it was used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

