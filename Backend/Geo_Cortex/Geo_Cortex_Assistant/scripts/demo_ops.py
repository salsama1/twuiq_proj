from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

import requests


BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
HERE = Path(__file__).resolve().parent
DEMO_DIR = HERE.parent / "demo_inputs"


def _read_geojson(name: str) -> Dict[str, Any]:
    p = DEMO_DIR / name
    return json.loads(p.read_text(encoding="utf-8"))


def _post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.post(f"{BASE_URL}{path}", json=payload, timeout=60)
    r.raise_for_status()
    return r.json()


def main() -> None:
    aoi1 = _read_geojson("aoi1.geojson")["features"][0]["geometry"]
    aoi2 = _read_geojson("aoi2.geojson")["features"][0]["geometry"]
    dissolve_fc = _read_geojson("dissolve_sample.geojson")
    join_fc = _read_geojson("join_polygons.geojson")

    print("== overlay: intersection ==")
    out = _post("/spatial/overlay", {"op": "intersection", "a": aoi1, "b": aoi2})
    print(json.dumps(out, indent=2)[:1500])

    print("\n== dissolve by 'group' ==")
    out = _post("/spatial/dissolve", {"feature_collection": dissolve_fc, "by_property": "group"})
    print(f"groups: {len(out.get('feature_collection', {}).get('features', []))}")

    print("\n== join counts (polygons -> MODS points) ==")
    out = _post("/spatial/join/mods/counts", {"feature_collection": join_fc, "predicate": "intersects", "id_property": "id"})
    feats = out.get("feature_collection", {}).get("features", [])
    for f in feats:
        print(f"{f.get('properties', {}).get('id')}: mods_count={f.get('properties', {}).get('mods_count')}")

    print("\n== join nearest (features -> nearest MODS point) ==")
    out = _post("/spatial/join/mods/nearest", {"feature_collection": join_fc, "id_property": "id"})
    for row in out.get("features", [])[:5]:
        print(f"{row.get('feature_id')}: distance_m={row.get('distance_m')}")


if __name__ == "__main__":
    main()

