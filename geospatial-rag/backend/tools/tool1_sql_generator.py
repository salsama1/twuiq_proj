"""
=============================================================================
GEOSPATIAL RAG - TOOL 1: SQL GENERATOR (FIXED & ENHANCED)
=============================================================================
- Correct schema for each table
- Saudi Arabia location awareness
- City/Region name understanding
- No default LIMIT
- Full PostGIS support
=============================================================================
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple

from llm.ollama_client import get_ollama_client
from database.postgis_client import get_postgis_client

logger = logging.getLogger(__name__)

# The actual SRID of the data
SOURCE_SRID = 3857
TARGET_SRID = 4326

# Saudi Arabia context - all data is in Saudi Arabia
SAUDI_REGIONS = {
    "riyadh": "Riyadh Region",
    "makkah": "Makkah Region", 
    "mecca": "Makkah Region",
    "madinah": "Madinah Region",
    "medina": "Madinah Region",
    "eastern": "Eastern Region",
    "asir": "Asir Region",
    "tabuk": "Tabuk Region",
    "hail": "Hail Region",
    "northern borders": "Northern Borders Region",
    "jazan": "Jazan Region",
    "najran": "Najran Region",
    "bahah": "Al Bahah Region",
    "jouf": "Al Jouf Region",
    "qassim": "Qassim Region"
}

# Major cities with approximate coordinates
SAUDI_CITIES = {
    "riyadh": (24.7136, 46.6753),
    "jeddah": (21.4858, 39.1925),
    "makkah": (21.4225, 39.8262),
    "mecca": (21.4225, 39.8262),
    "madinah": (24.5247, 39.5692),
    "medina": (24.5247, 39.5692),
    "dammam": (26.4207, 50.0888),
    "khobar": (26.2172, 50.1971),
    "dhahran": (26.2361, 50.0393),
    "taif": (21.2703, 40.4158),
    "tabuk": (28.3838, 36.5550),
    "buraidah": (26.3260, 43.9750),
    "abha": (18.2164, 42.5053),
    "najran": (17.4924, 44.1322),
    "jazan": (16.8892, 42.5511),
    "hail": (27.5114, 41.7208),
    "arar": (30.9753, 41.0381)
}


# Correct schema for each table - VERY IMPORTANT
DATABASE_SCHEMA = """
=== DATABASE CONTEXT ===
ALL DATA IS IN SAUDI ARABIA. When user says "Saudi Arabia" or "KSA", they mean ALL data.

=== TABLE: mods (Mineral Occurrences) ===
Columns:
- gid: integer PRIMARY KEY
- mods: varchar - MODS ID (e.g., "MODS 1159")
- eng_name: varchar - English name of the site
- arb_name: varchar - Arabic name (نام عربی)
- major_comm: varchar - Major commodities (Gold, Copper, Silver, etc.)
- minor_comm: varchar - Minor commodities
- trace_comm: varchar - Trace commodities
- region: varchar - Saudi region (e.g., "Riyadh Region", "Makkah Region")
- longitude: double - Original longitude
- latitude: double - Original latitude
- elevation: varchar - Altitude in meters
- occ_type: varchar - metallic/non-metallic
- exp_status: varchar - Exploration status
- occ_imp: varchar - Importance (Very high, High, Medium, Low, Very Low)
- host_rocks: varchar - Host rock types
- geologic_f: varchar - Geological formation
- gitology: varchar - Deposit type
- geom: geometry(Point) - Location point

=== TABLE: borholes (Borehole Data) - NOTE: spelled "borholes" not "boreholes" ===
Columns:
- gid: integer PRIMARY KEY
- project_id: varchar - Project identifier
- project_na: varchar - Project name
- borehole_i: varchar - Borehole ID
- borehole_t: varchar - Borehole type
- depth_m: varchar - Depth in meters
- longitude: double
- latitude: double
- elements: varchar - Chemical elements detected
- techn_data: varchar - Technical data
- mineral_co: varchar - Mineral composition
- pxrf: varchar - pXRF analysis data
- geom: geometry(Point)
** NO "region" column - use spatial join with mods if needed **

=== TABLE: surface_samples (Surface Samples) ===
Columns:
- gid: integer PRIMARY KEY
- projectid: varchar - Project identifier  
- projectnam: varchar - Project name
- sampleid: varchar - Sample ID
- sampletype: varchar - Sample type (rock, soil, stream sediment, etc.)
- longitude: double
- latitude: double
- elements: varchar - Chemical elements
- geom: geometry(Point)
** NO "region" column - use spatial join with mods if needed **

=== COORDINATE TRANSFORMATION (REQUIRED) ===
Data is stored in EPSG:3857 but labeled as 4326. ALWAYS use:
  ST_Y(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS latitude,
  ST_X(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS longitude

=== IMPORTANT RULES ===
1. NO LIMIT unless user specifically asks for a number
2. surface_samples and borholes do NOT have "region" column
3. Use ILIKE for case-insensitive search
4. "Saudi Arabia" means ALL data (no filter needed)
5. Table is "borholes" NOT "boreholes"
"""


SQL_GENERATOR_PROMPT = """You are an expert PostGIS SQL generator for a Saudi Arabian mining database.

{schema}

=== RESPONSE FORMAT (JSON only) ===
{{
    "sql_query": "SELECT ... FROM ... WHERE ...;",
    "query_type": "attribute|spatial|analysis|aggregate",
    "description": "Brief description",
    "tables_used": ["table1"]
}}

=== EXAMPLES ===

User: "Show all gold deposits"
{{
    "sql_query": "SELECT gid, eng_name, arb_name, major_comm, minor_comm, region, occ_imp, ST_Y(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS latitude, ST_X(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS longitude FROM mods WHERE major_comm ILIKE '%gold%' OR minor_comm ILIKE '%gold%';",
    "query_type": "attribute",
    "description": "Lists all gold deposits in Saudi Arabia",
    "tables_used": ["mods"]
}}

User: "Show surface samples in Makkah region"
Note: surface_samples has NO region column, must use spatial join or elements search
{{
    "sql_query": "SELECT s.gid, s.sampleid, s.projectnam, s.sampletype, s.elements, ST_Y(ST_Transform(ST_SetSRID(s.geom, 3857), 4326)) AS latitude, ST_X(ST_Transform(ST_SetSRID(s.geom, 3857), 4326)) AS longitude FROM surface_samples s WHERE s.geom IS NOT NULL;",
    "query_type": "attribute",
    "description": "Lists all surface samples (note: surface_samples table has no region column, showing all samples)",
    "tables_used": ["surface_samples"]
}}

User: "Show all boreholes"
{{
    "sql_query": "SELECT gid, project_na, borehole_i, borehole_t, depth_m, elements, ST_Y(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS latitude, ST_X(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS longitude FROM borholes WHERE geom IS NOT NULL;",
    "query_type": "attribute",
    "description": "Lists all boreholes with their details",
    "tables_used": ["borholes"]
}}

User: "Find sites in Riyadh Region"
{{
    "sql_query": "SELECT gid, eng_name, arb_name, major_comm, region, occ_imp, ST_Y(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS latitude, ST_X(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS longitude FROM mods WHERE region ILIKE '%Riyadh%';",
    "query_type": "attribute",
    "description": "Lists mineral sites in Riyadh Region",
    "tables_used": ["mods"]
}}

User: "Show all mines in Saudi Arabia"
{{
    "sql_query": "SELECT gid, eng_name, arb_name, major_comm, minor_comm, region, occ_imp, ST_Y(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS latitude, ST_X(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS longitude FROM mods WHERE geom IS NOT NULL;",
    "query_type": "attribute",
    "description": "Lists all mineral sites in Saudi Arabia (all data is in Saudi Arabia)",
    "tables_used": ["mods"]
}}

User: "Count minerals by region"
{{
    "sql_query": "SELECT region, COUNT(*) as count, STRING_AGG(DISTINCT major_comm, ', ') as commodities FROM mods WHERE region IS NOT NULL GROUP BY region ORDER BY count DESC;",
    "query_type": "aggregate",
    "description": "Counts mineral sites per region",
    "tables_used": ["mods"]
}}

User: "Find sites within 50km of Riyadh"
{{
    "sql_query": "SELECT gid, eng_name, major_comm, region, ST_Y(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS latitude, ST_X(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS longitude, ROUND((ST_Distance(ST_Transform(ST_SetSRID(geom, 3857), 4326)::geography, ST_SetSRID(ST_MakePoint(46.6753, 24.7136), 4326)::geography) / 1000)::numeric, 2) AS distance_km FROM mods WHERE ST_DWithin(ST_Transform(ST_SetSRID(geom, 3857), 4326)::geography, ST_SetSRID(ST_MakePoint(46.6753, 24.7136), 4326)::geography, 50000) ORDER BY distance_km;",
    "query_type": "spatial",
    "description": "Sites within 50km of Riyadh city center",
    "tables_used": ["mods"]
}}

User: "Find top 10 gold sites"
{{
    "sql_query": "SELECT gid, eng_name, arb_name, major_comm, region, occ_imp, ST_Y(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS latitude, ST_X(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS longitude FROM mods WHERE major_comm ILIKE '%gold%' ORDER BY CASE occ_imp WHEN 'Very high' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 WHEN 'Low' THEN 4 ELSE 5 END LIMIT 10;",
    "query_type": "attribute",
    "description": "Top 10 gold sites by importance",
    "tables_used": ["mods"]
}}

User: "Show samples with gold elements"
{{
    "sql_query": "SELECT gid, sampleid, projectnam, sampletype, elements, ST_Y(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS latitude, ST_X(ST_Transform(ST_SetSRID(geom, 3857), 4326)) AS longitude FROM surface_samples WHERE elements ILIKE '%Au%' OR elements ILIKE '%gold%';",
    "query_type": "attribute",
    "description": "Surface samples containing gold (Au)",
    "tables_used": ["surface_samples"]
}}
"""


class SQLGenerator:
    """Generates and executes PostGIS SQL from natural language."""
    
    def __init__(self):
        self.ollama = get_ollama_client()
        self.db = get_postgis_client()
    
    def _preprocess_query(self, query: str) -> str:
        """Preprocess the query to expand city/region names."""
        query_lower = query.lower()
        
        # Replace city names with region context
        for city, region in SAUDI_REGIONS.items():
            if city in query_lower:
                # Add region context
                query = query + f" (region: {region})"
                break
        
        # Add coordinate context for cities if distance query
        if any(word in query_lower for word in ['near', 'close', 'within', 'km', 'distance']):
            for city, coords in SAUDI_CITIES.items():
                if city in query_lower:
                    query = query + f" (coordinates: {coords[0]}, {coords[1]})"
                    break
        
        return query
    
    async def generate_sql(self, query: str) -> Dict[str, Any]:
        """Generate SQL from natural language query."""
        
        # Preprocess query
        processed_query = self._preprocess_query(query)
        
        prompt = SQL_GENERATOR_PROMPT.format(schema=DATABASE_SCHEMA)
        
        try:
            result = await self.ollama.generate_json(
                prompt=f'Convert to SQL: "{processed_query}"',
                system=prompt,
                temperature=0.0
            )
            
            if "sql_query" not in result:
                raise ValueError("No SQL query generated")
            
            sql = result["sql_query"]
            sql = self._fix_common_errors(sql)
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
    
    def _fix_common_errors(self, sql: str) -> str:
        """Fix common LLM mistakes."""
        
        # Fix boreholes -> borholes (actual table name)
        sql = re.sub(r'\bboreholes\b', 'borholes', sql, flags=re.IGNORECASE)
        
        # Fix region column usage in wrong tables
        # If querying surface_samples or borholes with region, remove that condition
        if 'surface_samples' in sql.lower() and 'region' in sql.lower():
            # Remove region conditions for surface_samples
            sql = re.sub(r"AND\s+\w*\.?region\s+ILIKE\s+'[^']*'", "", sql, flags=re.IGNORECASE)
            sql = re.sub(r"WHERE\s+\w*\.?region\s+ILIKE\s+'[^']*'\s+AND", "WHERE", sql, flags=re.IGNORECASE)
            sql = re.sub(r"WHERE\s+\w*\.?region\s+ILIKE\s+'[^']*'", "WHERE geom IS NOT NULL", sql, flags=re.IGNORECASE)
        
        if 'borholes' in sql.lower() and '.region' in sql.lower():
            sql = re.sub(r"AND\s+\w*\.?region\s+ILIKE\s+'[^']*'", "", sql, flags=re.IGNORECASE)
            sql = re.sub(r"WHERE\s+\w*\.?region\s+ILIKE\s+'[^']*'\s+AND", "WHERE", sql, flags=re.IGNORECASE)
            sql = re.sub(r"WHERE\s+\w*\.?region\s+ILIKE\s+'[^']*'", "WHERE geom IS NOT NULL", sql, flags=re.IGNORECASE)
        
        return sql
    
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
        
        return sql
    
    def validate_sql(self, sql: str) -> Tuple[bool, Optional[str]]:
        """Validate SQL query for safety."""
        return self.db.validate_query(sql)
    
    async def execute(self, query: str, max_rows: int = 50000) -> Dict[str, Any]:
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
