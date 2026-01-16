"""
=============================================================================
GEOSPATIAL RAG - TOOL 1: SQL GENERATOR (ENHANCED POSTGIS)
=============================================================================
Full PostGIS ST_* function support, no default LIMIT, complex query handling
=============================================================================
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple

from llm.ollama_client import get_ollama_client
from database.postgis_client import get_postgis_client, DATABASE_SCHEMA

logger = logging.getLogger(__name__)

# The actual SRID of the data (Web Mercator stored as 4326)
SOURCE_SRID = 3857
TARGET_SRID = 4326


SQL_GENERATOR_PROMPT = """You are an expert PostGIS SQL developer. Convert natural language queries to powerful PostGIS SQL.

{schema}

=== COORDINATE TRANSFORMATION ===
The geometry data is stored in Web Mercator (EPSG:3857) but labeled as 4326.
ALWAYS use this pattern to extract coordinates:
  ST_Y(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS latitude,
  ST_X(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS longitude

For spatial calculations, transform first:
  ST_Transform(ST_SetSRID(geom, 3857), 4326)

=== IMPORTANT RULES ===
1. DO NOT add LIMIT unless the user explicitly asks for a specific number
2. Use ILIKE for text searches (case-insensitive)
3. Never use DROP, DELETE, UPDATE, INSERT, ALTER

=== POSTGIS FUNCTIONS AVAILABLE ===
You can use ANY PostGIS function. Common ones:

**Measurement:**
- ST_Distance(geom1, geom2) - Distance between geometries
- ST_Length(geom) - Length of linestring
- ST_Area(geom) - Area of polygon
- ST_Perimeter(geom) - Perimeter of polygon

**Spatial Relationships:**
- ST_Within(geom1, geom2) - Is geom1 within geom2?
- ST_Contains(geom1, geom2) - Does geom1 contain geom2?
- ST_Intersects(geom1, geom2) - Do geometries intersect?
- ST_Overlaps(geom1, geom2) - Do geometries overlap?
- ST_Touches(geom1, geom2) - Do geometries touch?
- ST_Crosses(geom1, geom2) - Do geometries cross?
- ST_DWithin(geom1, geom2, distance) - Within distance?
- ST_Disjoint(geom1, geom2) - Are geometries disjoint?

**Geometry Processing:**
- ST_Buffer(geom, radius) - Create buffer around geometry
- ST_Union(geom1, geom2) - Union of geometries
- ST_Intersection(geom1, geom2) - Intersection
- ST_Difference(geom1, geom2) - Difference
- ST_ConvexHull(geom) - Convex hull
- ST_Centroid(geom) - Center point
- ST_Envelope(geom) - Bounding box

**Clustering:**
- ST_ClusterDBSCAN(geom, eps, minpoints) OVER() - Density clustering
- ST_ClusterKMeans(geom, k) OVER() - K-means clustering

**Distance & Nearest:**
- ST_Distance(geom1::geography, geom2::geography) - Distance in meters
- ST_DWithin(geom1::geography, geom2::geography, meters) - Within meters

**Construction:**
- ST_MakePoint(lon, lat) - Create point
- ST_SetSRID(geom, srid) - Set coordinate system
- ST_Transform(geom, srid) - Transform coordinates
- ST_MakeLine(geom1, geom2) - Create line
- ST_Collect(geom) - Collect geometries

**Output:**
- ST_AsText(geom) - WKT format
- ST_AsGeoJSON(geom) - GeoJSON format
- ST_X(point), ST_Y(point) - Get X/Y coordinates

=== RESPONSE FORMAT (JSON only) ===
{{
    "sql_query": "SELECT ... FROM ... WHERE ...;",
    "query_type": "attribute|spatial|analysis|aggregate",
    "description": "What the query does",
    "tables_used": ["table1"]
}}

=== EXAMPLES ===

User: "Find all gold deposits"
{{
    "sql_query": "SELECT gid, eng_name, arb_name, major_comm, minor_comm, region, occ_type, occ_imp, ST_Y(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS latitude, ST_X(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS longitude FROM mods WHERE major_comm ILIKE '%gold%' OR minor_comm ILIKE '%gold%' OR trace_comm ILIKE '%gold%';",
    "query_type": "attribute",
    "description": "Finds all gold deposits without limit",
    "tables_used": ["mods"]
}}

User: "Find sites within 50km of Riyadh (24.7136, 46.6753)"
{{
    "sql_query": "SELECT gid, eng_name, major_comm, region, ST_Y(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS latitude, ST_X(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS longitude, ROUND((ST_Distance(ST_Transform(ST_SetSRID(geom, 3857), 4326)::geography, ST_SetSRID(ST_MakePoint(46.6753, 24.7136), 4326)::geography) / 1000)::numeric, 2) AS distance_km FROM mods WHERE ST_DWithin(ST_Transform(ST_SetSRID(geom, 3857), 4326)::geography, ST_SetSRID(ST_MakePoint(46.6753, 24.7136), 4326)::geography, 50000) ORDER BY distance_km;",
    "query_type": "spatial",
    "description": "Finds all sites within 50km of Riyadh coordinates",
    "tables_used": ["mods"]
}}

User: "Cluster mineral sites using DBSCAN with 30km radius"
{{
    "sql_query": "SELECT gid, eng_name, major_comm, ST_ClusterDBSCAN(ST_Transform(ST_SetSRID(geom, 3857), 4326), eps := 0.3, minpoints := 3) OVER() AS cluster_id, ST_Y(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS latitude, ST_X(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS longitude FROM mods WHERE geom IS NOT NULL;",
    "query_type": "analysis",
    "description": "Clusters sites using DBSCAN algorithm",
    "tables_used": ["mods"]
}}

User: "Find nearest 10 sites to coordinate 23.5, 44.0"
{{
    "sql_query": "SELECT gid, eng_name, major_comm, region, ST_Y(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS latitude, ST_X(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS longitude, ROUND((ST_Distance(ST_Transform(ST_SetSRID(geom, 3857), 4326)::geography, ST_SetSRID(ST_MakePoint(44.0, 23.5), 4326)::geography) / 1000)::numeric, 2) AS distance_km FROM mods WHERE geom IS NOT NULL ORDER BY ST_Distance(ST_Transform(ST_SetSRID(geom, 3857), 4326)::geography, ST_SetSRID(ST_MakePoint(44.0, 23.5), 4326)::geography) LIMIT 10;",
    "query_type": "spatial",
    "description": "Finds 10 nearest sites to specified coordinates",
    "tables_used": ["mods"]
}}

User: "Count minerals by region and show top 10"
{{
    "sql_query": "SELECT region, COUNT(*) as count, STRING_AGG(DISTINCT major_comm, ', ') as commodities FROM mods WHERE region IS NOT NULL AND region != '' GROUP BY region ORDER BY count DESC LIMIT 10;",
    "query_type": "aggregate",
    "description": "Shows top 10 regions by mineral count",
    "tables_used": ["mods"]
}}

User: "Find gold and copper sites in the same region"
{{
    "sql_query": "SELECT DISTINCT g.region, COUNT(DISTINCT g.gid) as gold_count, COUNT(DISTINCT c.gid) as copper_count FROM mods g JOIN mods c ON g.region = c.region WHERE (g.major_comm ILIKE '%gold%' OR g.minor_comm ILIKE '%gold%') AND (c.major_comm ILIKE '%copper%' OR c.minor_comm ILIKE '%copper%') GROUP BY g.region ORDER BY gold_count + copper_count DESC;",
    "query_type": "analysis",
    "description": "Finds regions with both gold and copper deposits",
    "tables_used": ["mods"]
}}

User: "Show all boreholes"
{{
    "sql_query": "SELECT gid, project_na, borehole_i, borehole_t, depth_m, elements, ST_Y(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS latitude, ST_X(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS longitude FROM borholes WHERE geom IS NOT NULL;",
    "query_type": "attribute",
    "description": "Shows all boreholes with their details",
    "tables_used": ["borholes"]
}}

User: "Find surface samples with high gold content"
{{
    "sql_query": "SELECT gid, sampleid, projectnam, sampletype, elements, ST_Y(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS latitude, ST_X(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS longitude FROM surface_samples WHERE elements ILIKE '%Au%' OR elements ILIKE '%gold%';",
    "query_type": "attribute",
    "description": "Finds surface samples containing gold",
    "tables_used": ["surface_samples"]
}}

User: "Calculate convex hull of all gold deposits"
{{
    "sql_query": "SELECT ST_AsGeoJSON(ST_ConvexHull(ST_Collect(ST_Transform(ST_SetSRID(geom, 3857), 4326)))) as convex_hull, COUNT(*) as point_count FROM mods WHERE major_comm ILIKE '%gold%';",
    "query_type": "analysis",
    "description": "Creates convex hull polygon around all gold deposits",
    "tables_used": ["mods"]
}}
"""


class SQLGenerator:
    """Generates and executes PostGIS SQL from natural language."""
    
    def __init__(self):
        self.ollama = get_ollama_client()
        self.db = get_postgis_client()
        self.schema = DATABASE_SCHEMA
        self.source_srid = SOURCE_SRID
        self.target_srid = TARGET_SRID
    
    async def generate_sql(self, query: str) -> Dict[str, Any]:
        """Generate SQL from natural language query."""
        prompt = SQL_GENERATOR_PROMPT.format(schema=self.schema)
        
        try:
            result = await self.ollama.generate_json(
                prompt=f"Convert to SQL: \"{query}\"",
                system=prompt,
                temperature=0.0
            )
            
            if "sql_query" not in result:
                raise ValueError("No SQL query generated")
            
            sql = result["sql_query"]
            sql = self._ensure_coordinate_transform(sql)
            
            return {
                "sql_query": sql,
                "query_type": result.get("query_type", "unknown"),
                "description": result.get("description", ""),
                "tables_used": result.get("tables_used", [])
            }
            
        except Exception as e:
            logger.error(f"SQL generation failed: {e}")
            raise ValueError(f"Failed to generate SQL: {e}")
    
    def _ensure_coordinate_transform(self, sql: str) -> str:
        """Ensure SQL uses correct ST_Transform with ST_SetSRID."""
        
        # Fix ST_Y(geom) -> ST_Y(ST_Transform(ST_SetSRID(geom, 3857), 4326))
        sql = re.sub(
            r'ST_Y\(geom\)',
            'ST_Y(ST_Transform(ST_SetSRID(geom, 3857), 4326))',
            sql,
            flags=re.IGNORECASE
        )
        
        sql = re.sub(
            r'ST_X\(geom\)',
            'ST_X(ST_Transform(ST_SetSRID(geom, 3857), 4326))',
            sql,
            flags=re.IGNORECASE
        )
        
        # Fix aliased versions
        sql = re.sub(
            r'ST_Y\((\w+)\.geom\)',
            r'ST_Y(ST_Transform(ST_SetSRID(\1.geom, 3857), 4326))',
            sql,
            flags=re.IGNORECASE
        )
        
        sql = re.sub(
            r'ST_X\((\w+)\.geom\)',
            r'ST_X(ST_Transform(ST_SetSRID(\1.geom, 3857), 4326))',
            sql,
            flags=re.IGNORECASE
        )
        
        # Fix ST_Transform(geom, 4326) without SetSRID
        sql = re.sub(
            r'ST_Transform\(geom,\s*4326\)',
            'ST_Transform(ST_SetSRID(geom, 3857), 4326)',
            sql,
            flags=re.IGNORECASE
        )
        
        return sql
    
    def validate_sql(self, sql: str) -> Tuple[bool, Optional[str]]:
        """Validate SQL query for safety."""
        return self.db.validate_query(sql)
    
    async def execute(self, query: str, max_rows: int = 10000) -> Dict[str, Any]:
        """Generate SQL, validate, and execute."""
        
        generation_result = await self.generate_sql(query)
        sql = generation_result["sql_query"]
        
        is_valid, error = self.validate_sql(sql)
        if not is_valid:
            return {
                "success": False,
                "error": f"Invalid SQL: {error}",
                "sql_query": sql,
                "natural_query": query
            }
        
        try:
            results, was_truncated = self.db.execute_safe_query(sql, max_rows)
            
            return {
                "success": True,
                "data": results,
                "row_count": len(results),
                "was_truncated": was_truncated,
                "sql_query": sql,
                "query_type": generation_result["query_type"],
                "description": generation_result["description"],
                "tables_used": generation_result["tables_used"],
                "natural_query": query
            }
            
        except Exception as e:
            logger.error(f"SQL execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "sql_query": sql,
                "natural_query": query
            }


_sql_generator: Optional[SQLGenerator] = None

def get_sql_generator() -> SQLGenerator:
    """Get or create the global SQL generator."""
    global _sql_generator
    if _sql_generator is None:
        _sql_generator = SQLGenerator()
    return _sql_generator
