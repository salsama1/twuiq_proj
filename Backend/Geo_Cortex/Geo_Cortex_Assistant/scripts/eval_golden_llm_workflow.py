from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List

import requests


BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
# Keep default timeout moderate so evaluation finishes quickly on local models.
TIMEOUT_SEC = float(os.getenv("EVAL_TIMEOUT_SEC", "45"))

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = Path(os.getenv("LLM_GOLDEN_PATH", str(ROOT / "eval" / "golden_llm_workflow.jsonl")))


def _load() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not GOLDEN.exists():
        return items
    for line in GOLDEN.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        items.append(json.loads(line))
    return items


def main() -> int:
    items = _load()
    if not items:
        print(f"No golden file found at {GOLDEN}. Generate one with: python scripts/generate_golden_llm_workflow.py")
        return 1

    # Evaluating many LLM calls can take a long time on local models.
    # By default, evaluate a subset and report metrics on that sample.
    max_items = int(os.getenv("EVAL_MAX_ITEMS", "50"))
    seed = int(os.getenv("EVAL_SEED", "1337"))
    if max_items > 0 and len(items) > max_items:
        import random

        random.seed(seed)
        items = random.sample(items, max_items)

    validated_ok = 0
    total = 0
    llm_used = 0
    llm_used_ok = 0
    lat_ms: List[float] = []
    violations: Dict[str, int] = {}
    failures = 0

    for it in items:
        payload = it.get("payload") or {}
        try:
            t0 = time.perf_counter()
            r = requests.post(f"{BASE_URL}/agent/workflow", json=payload, timeout=TIMEOUT_SEC)
            ms = (time.perf_counter() - t0) * 1000.0
            lat_ms.append(ms)
            r.raise_for_status()
            j = r.json()
            artifacts = j.get("artifacts") or {}
        except Exception as e:
            failures += 1
            total += 1
            violations[str(type(e).__name__)] = violations.get(str(type(e).__name__), 0) + 1
            continue

        total += 1
        if artifacts.get("summary_validated") is True:
            validated_ok += 1
        src = artifacts.get("summary_source")
        if src == "llm":
            llm_used += 1
            if artifacts.get("summary_validated") is True:
                llm_used_ok += 1

        for v in artifacts.get("summary_violations") or []:
            violations[str(v)] = violations.get(str(v), 0) + 1

    sys_rate = validated_ok / total if total else 0.0
    llm_rate = llm_used_ok / llm_used if llm_used else 0.0
    llm_used_rate = llm_used / total if total else 0.0

    print(f"golden_items: {total}")
    print(f"request_failures: {failures}")
    print(f"system_validated_rate: {sys_rate:.3f} ({validated_ok}/{total})")
    print(f"llm_validated_rate (when used): {llm_rate:.3f} ({llm_used_ok}/{llm_used})")
    print(f"llm_used_rate: {llm_used_rate:.3f} ({llm_used}/{total})")
    if lat_ms:
        print(f"latency_ms: p50={statistics.median(lat_ms):.1f}  max={max(lat_ms):.1f}  mean={statistics.mean(lat_ms):.1f}")
    if violations:
        print("violations:")
        for k, v in sorted(violations.items(), key=lambda x: (-x[1], x[0]))[:10]:
            print(f"- {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

