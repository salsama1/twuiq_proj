from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure imports work when running as a script (python scripts/generate_golden_rag.py)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models.dbmodels import MODSOccurrence


OUT_DIR = ROOT / "eval"
OUT_PATH = OUT_DIR / "golden_rag.jsonl"


TEMPLATES = [
    # name-only
    lambda name, mods_id: f"Tell me about {name}.",
    lambda name, mods_id: f"Give me details on {name}.",
    lambda name, mods_id: f"What is {name}?",
    # include MODS id
    lambda name, mods_id: f"Tell me about {name}. MODS ID: {mods_id}.",
    lambda name, mods_id: f"Find record MODS ID {mods_id} and summarize it.",
]


def _sample_rows(n: int) -> List[Tuple[str, str, str, str]]:
    """
    Return [(mods_id, english_name, admin_region, major_commodity)].
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(
                MODSOccurrence.mods_id,
                MODSOccurrence.english_name,
                MODSOccurrence.admin_region,
                MODSOccurrence.major_commodity,
            )
            .filter(MODSOccurrence.mods_id.isnot(None))
            .filter(MODSOccurrence.mods_id != "")
            .filter(MODSOccurrence.english_name.isnot(None))
            .filter(MODSOccurrence.english_name != "")
            .limit(20000)
            .all()
        )
    finally:
        db.close()

    clean: List[Tuple[str, str, str, str]] = []
    for m, nm, reg, com in rows:
        clean.append((str(m), str(nm), str(reg or ""), str(com or "")))
    random.shuffle(clean)
    return clean[:n]


def main() -> int:
    n = int(os.getenv("GOLDEN_RAG_N", "300"))
    seed = int(os.getenv("GOLDEN_SEED", "1337"))
    random.seed(seed)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = _sample_rows(n)
    if not rows:
        print("No rows in DB. Load MODS into PostGIS first.")
        return 1

    items: List[Dict[str, Any]] = []
    for mods_id, name, region, commodity in rows:
        tmpl = random.choice(TEMPLATES)
        query = tmpl(name, mods_id)
        items.append(
            {
                "id": f"{mods_id}|{abs(hash(query))%1_000_000}",
                "query": query,
                "expected_mods_ids": [mods_id],
                "meta": {"english_name": name, "admin_region": region, "major_commodity": commodity},
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

