from __future__ import annotations

import sys
from pathlib import Path
import os
import random
import time
from typing import Any, Dict, List, Tuple

# Ensure imports work when running as a script (python scripts/eval_rag_recall.py)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models.dbmodels import MODSOccurrence
from app.services.router_service import rag_retrieve


def _pick_samples(db, n: int) -> List[Tuple[str, str]]:
    """
    Return [(mods_id, english_name)] samples.
    """
    rows = (
        db.query(MODSOccurrence.mods_id, MODSOccurrence.english_name)
        .filter(MODSOccurrence.mods_id.isnot(None))
        .filter(MODSOccurrence.mods_id != "")
        .filter(MODSOccurrence.english_name.isnot(None))
        .filter(MODSOccurrence.english_name != "")
        .limit(5000)
        .all()
    )
    rows2 = [(str(m), str(nm)) for (m, nm) in rows if m and nm]
    if not rows2:
        return []
    random.shuffle(rows2)
    return rows2[:n]


def main() -> int:
    n = int(os.getenv("RAG_EVAL_N", "50"))
    ks_env = os.getenv("RAG_KS", "5,10,20")
    ks = []
    for part in ks_env.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ks.append(int(part))
        except Exception:
            continue
    ks = [k for k in ks if k > 0] or [5]

    db = SessionLocal()
    try:
        samples = _pick_samples(db, n=n)
    finally:
        db.close()

    if not samples:
        print("No samples found in mods_occurrences. Did you load MODS.csv into the DB?")
        return 1

    # Evaluate for multiple k values
    def _run(template_name: str, make_query) -> None:
        for k in ks:
            hits = 0
            total = 0
            times_ms = []
            misses: List[Dict[str, Any]] = []

            for mods_id, english_name in samples:
                q = make_query(mods_id, english_name)
                t0 = time.perf_counter()
                _ctx, occs = rag_retrieve(q, k=k)
                ms = (time.perf_counter() - t0) * 1000.0
                times_ms.append(ms)

                found = False
                for o in occs or []:
                    try:
                        if str(o.mods_id).strip() == str(mods_id).strip():
                            found = True
                            break
                    except Exception:
                        continue
                total += 1
                if found:
                    hits += 1
                else:
                    misses.append({"mods_id": mods_id, "english_name": english_name})

            recall = (hits / total) if total else 0.0
            avg_ms = sum(times_ms) / len(times_ms) if times_ms else 0.0

            print(f"\n[{template_name}] recall@{k}: {recall:.3f} ({hits}/{total})")
            print(f"[{template_name}] retrieval_time_ms: avg={avg_ms:.1f}  max={max(times_ms) if times_ms else 0.0:.1f}")
            if misses:
                print(f"[{template_name}] misses: {len(misses)} (showing up to 10)")
                for m in misses[:10]:
                    print(f"- {m['mods_id']}: {m['english_name']}")

    _run(
        "name+mods_id",
        lambda mods_id, english_name: f"Tell me about {english_name}. MODS ID: {mods_id}.",
    )
    _run(
        "name_only",
        lambda _mods_id, english_name: f"Tell me about {english_name}.",
    )

    print("\nNotes:")
    print("- This tests retrieval (FAISS) only; it does not evaluate the LLM answer quality.")
    print("- If recall is low, try rebuilding the vectorstore or tuning chunking/metadata in build_vectorstore.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

