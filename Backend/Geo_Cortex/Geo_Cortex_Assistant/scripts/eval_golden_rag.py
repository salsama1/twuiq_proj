from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.router_service import rag_retrieve  # noqa: E402


GOLDEN = Path(os.getenv("RAG_GOLDEN_PATH", str(ROOT / "eval" / "golden_rag.jsonl")))


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


def _hit(expected: List[str], occs: Any) -> bool:
    exp = {str(x).strip().upper() for x in (expected or [])}
    for o in occs or []:
        try:
            mid = str(o.mods_id).strip().upper()
        except Exception:
            continue
        if mid in exp:
            return True
    return False


def main() -> int:
    k = int(os.getenv("RAG_K", "5"))
    items = _load()
    if not items:
        print(f"No golden file found at {GOLDEN}. Generate one with: python scripts/generate_golden_rag.py")
        return 1

    hits = 0
    total = 0
    times: List[float] = []
    misses: List[Tuple[str, str, List[str]]] = []

    for it in items:
        q = str(it.get("query") or "")
        exp = it.get("expected_mods_ids") or []
        t0 = time.perf_counter()
        _ctx, occs = rag_retrieve(q, k=k)
        ms = (time.perf_counter() - t0) * 1000.0
        times.append(ms)
        total += 1
        if _hit(exp, occs):
            hits += 1
        else:
            misses.append((str(it.get("id")), q, list(exp)))

    recall = hits / total if total else 0.0
    print(f"golden_items: {total}")
    print(f"recall@{k}: {recall:.3f} ({hits}/{total})")
    if times:
        print(f"retrieval_ms: avg={sum(times)/len(times):.1f}  max={max(times):.1f}")
    if misses:
        print(f"misses: {len(misses)} (showing up to 10)")
        for mid, q, exp in misses[:10]:
            print(f"- {mid} expected={exp} query={q[:120]}")
    return 0


if __name__ == "__main__":
    # Ensure imports work when running as a script
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    raise SystemExit(main())

