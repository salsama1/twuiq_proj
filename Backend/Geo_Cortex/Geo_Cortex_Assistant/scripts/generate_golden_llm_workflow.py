from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "eval"
OUT_PATH = OUT_DIR / "golden_llm_workflow.jsonl"


PROMPTS = [
    "Run QC summary and top commodities, then generate charts.",
    "Give me counts by region and top commodities, and summarize.",
    "Generate a density/heatmap view and summarize what it means.",
    "Run QC outliers and explain what should be checked next.",
    "Summarize the most important patterns by region (counts + charts).",
]


def main() -> int:
    n = int(os.getenv("GOLDEN_LLM_N", "150"))
    seed = int(os.getenv("GOLDEN_SEED", "1337"))
    random.seed(seed)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items: List[Dict[str, Any]] = []
    for i in range(n):
        q = random.choice(PROMPTS)
        items.append(
            {
                "id": f"wf_{i:04d}",
                "payload": {"query": q, "max_steps": 10, "use_llm": True},
                # what we evaluate: summary_validated must be true; summary_source preferably "llm"
                "expect": {"summary_validated": True},
            }
        )

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for obj in items:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    print(f"Wrote {len(items)} items to {OUT_PATH}")
    print("Tip: keep this file frozen (commit it) for a defensible claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

