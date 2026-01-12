from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def ensure_postgis_and_indexes(engine: Engine) -> None:
    """
    Best-effort DB maintenance for local PostGIS usage.
    Never raises: failure here should not prevent API boot.
    """
    try:
        if engine.dialect.name != "postgresql":
            return
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))

            # Ensure a GiST index exists for geom (for fast ST_DWithin/ST_Distance).
            exists = conn.execute(
                text(
                    """
                    SELECT 1
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND tablename = 'mods_occurrences'
                      AND indexdef ILIKE '%USING gist%'
                      AND indexdef ILIKE '%(geom%';
                    """
                )
            ).first()
            if not exists:
                conn.execute(
                    text("CREATE INDEX IF NOT EXISTS mods_occurrences_geom_gist ON mods_occurrences USING GIST (geom)")
                )
    except Exception:
        return

