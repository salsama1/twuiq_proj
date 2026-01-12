from __future__ import annotations

import json
import tempfile
from typing import Any, Dict, List, Optional

import gpxpy
from fastkml import kml
from shapely.geometry import mapping, shape
from shapely.ops import unary_union
from shapely import wkt as shapely_wkt


def _as_feature(geom: Dict[str, Any], props: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"type": "Feature", "geometry": geom, "properties": props or {}}


def _to_feature_collection(features: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}


def _normalize_geojson(obj: Dict[str, Any]) -> Dict[str, Any]:
    t = (obj.get("type") or "").strip()
    if t == "FeatureCollection":
        feats = obj.get("features") or []
        feats = [f for f in feats if isinstance(f, dict)]
        return {"type": "FeatureCollection", "features": feats}
    if t == "Feature":
        geom = obj.get("geometry")
        if not isinstance(geom, dict):
            raise ValueError("GeoJSON Feature missing geometry")
        return _to_feature_collection([_as_feature(geom, obj.get("properties") if isinstance(obj.get("properties"), dict) else {})])
    # assume geometry
    return _to_feature_collection([_as_feature(obj, {})])


def parse_geojson_bytes(data: bytes) -> Dict[str, Any]:
    obj = json.loads(data.decode("utf-8-sig"))
    if not isinstance(obj, dict):
        raise ValueError("GeoJSON must be an object")
    return _normalize_geojson(obj)


def parse_wkt_text(text: str) -> Dict[str, Any]:
    g = shapely_wkt.loads(text.strip())
    return _to_feature_collection([_as_feature(mapping(g), {})])


def parse_gpx_bytes(data: bytes) -> Dict[str, Any]:
    gpx = gpxpy.parse(data.decode("utf-8", errors="replace"))
    features: List[Dict[str, Any]] = []
    # Waypoints -> Points
    for w in gpx.waypoints or []:
        features.append(_as_feature({"type": "Point", "coordinates": [w.longitude, w.latitude]}, {"name": w.name}))
    # Tracks -> LineStrings
    for trk in gpx.tracks or []:
        for seg in trk.segments or []:
            coords = [[p.longitude, p.latitude] for p in seg.points or []]
            if len(coords) >= 2:
                features.append(_as_feature({"type": "LineString", "coordinates": coords}, {"name": trk.name}))
    # Routes -> LineStrings
    for rte in gpx.routes or []:
        coords = [[p.longitude, p.latitude] for p in rte.points or []]
        if len(coords) >= 2:
            features.append(_as_feature({"type": "LineString", "coordinates": coords}, {"name": rte.name}))
    return _to_feature_collection(features)


def parse_kml_bytes(data: bytes) -> Dict[str, Any]:
    doc = kml.KML()
    doc.from_string(data)
    features: List[Dict[str, Any]] = []

    def walk(f):
        try:
            for c in f.features():
                yield c
                yield from walk(c)
        except Exception:
            return

    for feat in walk(doc):
        try:
            geom = getattr(feat, "geometry", None)
            if geom is None:
                continue
            # fastkml uses pygeoif geometry; mapping via shapely by converting to geojson-like dict
            geom_dict = json.loads(geom.geojson) if hasattr(geom, "geojson") else None
            if isinstance(geom_dict, dict) and geom_dict.get("type"):
                props = {}
                name = getattr(feat, "name", None)
                if name:
                    props["name"] = name
                features.append(_as_feature(geom_dict, props))
        except Exception:
            continue

    return _to_feature_collection(features)


def parse_geofile(
    filename: str,
    content_type: Optional[str],
    data: bytes,
) -> Dict[str, Any]:
    """
    Parse common geospatial file formats into GeoJSON FeatureCollection.

    Supported (pure python):
    - .geojson/.json (GeoJSON)
    - .kml
    - .gpx
    - .wkt/.txt (WKT geometry)

    Supported (optional GDAL stack):
    - .gpkg (GeoPackage)
    - .zip (zipped Shapefile or zipped FileGDB)
    """
    name = (filename or "").lower()
    ct = (content_type or "").lower()

    if name.endswith((".geojson", ".json")) or "geo+json" in ct or ct == "application/json":
        return parse_geojson_bytes(data)
    if name.endswith(".kml") or "kml" in ct:
        return parse_kml_bytes(data)
    if name.endswith(".gpx") or "gpx" in ct:
        return parse_gpx_bytes(data)
    if name.endswith((".wkt", ".txt")) or "wkt" in ct:
        return parse_wkt_text(data.decode("utf-8", errors="replace"))

    if name.endswith(".gpkg") or name.endswith(".zip") or "geopackage" in ct or "x-gis" in ct:
        return _parse_with_gdal_stack(filename or "upload", data)

    raise ValueError(f"Unsupported geospatial file type: {filename or ct or 'unknown'}")


def featurecollection_to_union_geometry(fc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Union all feature geometries into a single GeoJSON geometry.
    """
    feats = fc.get("features") or []
    shapes = []
    for f in feats:
        geom = (f or {}).get("geometry")
        if isinstance(geom, dict) and geom.get("type"):
            try:
                shapes.append(shape(geom))
            except Exception:
                continue
    if not shapes:
        raise ValueError("No valid geometries found in uploaded file")
    u = unary_union(shapes)
    return mapping(u)  # GeoJSON geometry dict


def _gdal_available() -> bool:
    try:
        import fiona  # noqa: F401

        return True
    except Exception:
        return False


def _parse_with_gdal_stack(filename: str, data: bytes) -> Dict[str, Any]:
    """
    Parse GDAL-backed formats using Fiona.
    - GeoPackage: .gpkg (single file)
    - Zipped Shapefile/FileGDB: .zip (uses GDAL virtual file system)
    """
    try:
        import fiona
    except Exception as e:
        raise ValueError(
            "GDAL-backed formats (GeoPackage/Shapefile/FileGDB) require optional dependencies. "
            "Install with: pip install -r requirements-gdal.txt "
            "(on Windows, Conda is often easiest)."
        ) from e

    lower = (filename or "").lower()

    # Write upload to a temp file on disk (Fiona expects a path)
    if lower.endswith(".zip"):
        suffix = ".zip"
    elif lower.endswith(".gpkg"):
        suffix = ".gpkg"
    else:
        # fallback: try as zip first
        suffix = ".zip"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(data)
        tmp.flush()

        path = tmp.name
        # For zip, Fiona can use GDAL's /vsizip/ via "zip://"
        if suffix == ".zip":
            open_path = f"zip://{path}"
        else:
            open_path = path

        features: List[Dict[str, Any]] = []
        try:
            # If multiple layers exist (gpkg/fgdb), read first by default.
            layers = []
            try:
                layers = list(fiona.listlayers(open_path))
            except Exception:
                layers = []

            if layers:
                src = fiona.open(open_path, layer=layers[0])
            else:
                src = fiona.open(open_path)

            with src:
                for feat in src:
                    if not isinstance(feat, dict):
                        continue
                    geom = feat.get("geometry")
                    if not isinstance(geom, dict) or not geom.get("type"):
                        continue
                    props = feat.get("properties") if isinstance(feat.get("properties"), dict) else {}
                    features.append(_as_feature(geom, dict(props or {})))
                    # hard cap to avoid huge uploads blowing up memory
                    if len(features) >= 50000:
                        break
        except Exception as e:
            raise ValueError(f"Failed to parse GDAL-backed file: {e}") from e

        return _to_feature_collection(features)

