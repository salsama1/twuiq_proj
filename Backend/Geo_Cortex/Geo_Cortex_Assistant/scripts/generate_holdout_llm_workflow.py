from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "eval"
OUT_PATH = OUT_DIR / "holdout_llm_workflow.jsonl"


# Different prompt set than golden, to reduce “prompt template leakage”.
PROMPTS = [
    "Summarize QA/QC issues (duplicates and outliers) and suggest next checks. Keep it brief.",
    "Give a short summary of patterns by region and what to visualize next.",
    "Generate charts for top commodities and explain what those charts show (no raw rows).",
    "Run a density/heatmap style aggregation and describe hotspots at a high level.",
    "Summarize spatial results totals if any were computed, and provide GIS-ready outputs if relevant.",
]


def main() -> int:
    n = int(os.getenv("HOLDOUT_LLM_N", "150"))
    seed = int(os.getenv("HOLDOUT_SEED", "7331"))
    random.seed(seed)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items: List[Dict[str, Any]] = []
    for i in range(n):
        q = random.choice(PROMPTS)
        items.append(
            {
                "id": f"holdout_wf_{i:04d}",
                "payload": {"query": q, "max_steps": 10, "use_llm": True},
                "expect": {"summary_validated": True},
            }
        )

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for obj in items:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    print(f"Wrote {len(items)} items to {OUT_PATH}")
    print("Tip: keep this file frozen (commit it) as a true holdout set.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

