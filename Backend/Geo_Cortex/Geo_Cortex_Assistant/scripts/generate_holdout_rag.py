from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure imports work when running as a script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models.dbmodels import MODSOccurrence  # noqa: E402


OUT_DIR = ROOT / "eval"
OUT_PATH = OUT_DIR / "holdout_rag.jsonl"


# Different phrasing patterns than the golden generator (to reduce “template leakage”).
TEMPLATES = [
    lambda name, mods_id: f"Summarize {name}.",
    lambda name, mods_id: f"Provide a short description of {name}.",
    lambda name, mods_id: f"Where is {name} located and what is the major commodity?",
    lambda name, mods_id: f"I’m looking for {name} (MODS: {mods_id}).",
    lambda name, mods_id: f"Find {mods_id} and tell me the key attributes.",
]


def _sample_rows(n: int) -> List[Tuple[str, str, str, str]]:
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
    n = int(os.getenv("HOLDOUT_RAG_N", "300"))
    seed = int(os.getenv("HOLDOUT_SEED", "7331"))
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
    print("Tip: keep this file frozen (commit it) as a true holdout set.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

