"""
Script to load MODS.csv data into the database
Run this after setting up the database to populate the MODSOccurrence table.
"""
import os
import sys
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import text
from dotenv import load_dotenv
from geoalchemy2.elements import WKTElement

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, engine, Base
from app.models.dbmodels import MODSOccurrence

load_dotenv()

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODS_CSV_PATH = os.path.join(BASE_DIR, "MODS.csv")


def load_mods_to_db():
    """Load MODS.csv data into database"""
    print("Ensuring PostGIS extension is enabled...")
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))

    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    
    print(f"Loading MODS.csv from {MODS_CSV_PATH}...")
    
    if not os.path.exists(MODS_CSV_PATH):
        raise FileNotFoundError(f"MODS.csv not found at {MODS_CSV_PATH}")
    
    # Load CSV
    df = pd.read_csv(MODS_CSV_PATH)
    print(f"Loaded {len(df)} rows from MODS.csv")
    
    db = SessionLocal()
    
    try:
        # Clear existing data (optional - comment out if you want to keep existing data)
        print("Clearing existing MODS occurrences...")
        db.query(MODSOccurrence).delete()
        db.commit()
        
        # Insert data
        print("Inserting data into database...")
        for idx, row in df.iterrows():
            try:
                occurrence = MODSOccurrence(
                    mods_id=str(row.get('MODS', '')),
                    english_name=str(row.get('English Name', '')) if pd.notna(row.get('English Name')) else '',
                    arabic_name=str(row.get('Arabic Name', '')) if pd.notna(row.get('Arabic Name')) else None,
                    library_reference=str(row.get('Library Reference', '')) if pd.notna(row.get('Library Reference')) else None,
                    major_commodity=str(row.get('Major Commodity', '')) if pd.notna(row.get('Major Commodity')) else '',
                    longitude=float(row.get('Longitude', 0)) if pd.notna(row.get('Longitude')) else 0.0,
                    latitude=float(row.get('Latitude', 0)) if pd.notna(row.get('Latitude')) else 0.0,
                    geom=(
                        WKTElement(
                            f"POINT({float(row.get('Longitude'))} {float(row.get('Latitude'))})",
                            srid=4326,
                        )
                        if pd.notna(row.get('Longitude')) and pd.notna(row.get('Latitude'))
                        else None
                    ),
                    quadrangle=str(row.get('Quadrangle', '')) if pd.notna(row.get('Quadrangle')) else None,
                    admin_region=str(row.get('Admin Region', '')) if pd.notna(row.get('Admin Region')) else None,
                    elevation=float(row.get('Elevation', 0)) if pd.notna(row.get('Elevation')) else None,
                    occurrence_type=str(row.get('Occurrence Type', '')) if pd.notna(row.get('Occurrence Type')) else None,
                    input_date=str(row.get('Input Date', '')) if pd.notna(row.get('Input Date')) else None,
                    last_update=str(row.get('Last Update', '')) if pd.notna(row.get('Last Update')) else None,
                    position_origin=str(row.get('Position Origin', '')) if pd.notna(row.get('Position Origin')) else None,
                    exploration_status=str(row.get('Exploration Status', '')) if pd.notna(row.get('Exploration Status')) else None,
                    security_status=str(row.get('Security Status', '')) if pd.notna(row.get('Security Status')) else None,
                    occurrence_importance=str(row.get('Occurrence Importance', '')) if pd.notna(row.get('Occurrence Importance')) else None,
                    occurrence_status=str(row.get('Occurrence Status', '')) if pd.notna(row.get('Occurrence Status')) else None,
                    ancient_workings=str(row.get('Ancient Workings', '')) if pd.notna(row.get('Ancient Workings')) else None,
                    geochemical_exploration=str(row.get('Geochemical Exploration', '')) if pd.notna(row.get('Geochemical Exploration')) else None,
                    geophysical_exploration=str(row.get('Geophysical Exploration', '')) if pd.notna(row.get('Geophysical Exploration')) else None,
                    mapping_exploration=str(row.get('Mapping Exploration', '')) if pd.notna(row.get('Mapping Exploration')) else None,
                    exploration_data=str(row.get('Exploration Data', '')) if pd.notna(row.get('Exploration Data')) else None,
                    structural_province=str(row.get('Structural Province', '')) if pd.notna(row.get('Structural Province')) else None,
                    regional_structure=str(row.get('Regional Structure', '')) if pd.notna(row.get('Regional Structure')) else None,
                    geologic_group=str(row.get('Geologic Group', '')) if pd.notna(row.get('Geologic Group')) else None,
                    geologic_formation=str(row.get('Geologic Formation', '')) if pd.notna(row.get('Geologic Formation')) else None,
                    host_rocks=str(row.get('Host Rocks', '')) if pd.notna(row.get('Host Rocks')) else None,
                    country_rocks=str(row.get('Country Rocks', '')) if pd.notna(row.get('Country Rocks')) else None,
                    geology=str(row.get('Gitology', '')) if pd.notna(row.get('Gitology')) else None,
                    mineralization_control=str(row.get('Mineralization Control', '')) if pd.notna(row.get('Mineralization Control')) else None,
                    alteration=str(row.get('Alteration', '')) if pd.notna(row.get('Alteration')) else None,
                    mineralization_morphology=str(row.get('Mineralization Morphology', '')) if pd.notna(row.get('Mineralization Morphology')) else None,
                    minor_commodities=str(row.get('Minor Commodities', '')) if pd.notna(row.get('Minor Commodities')) else None,
                    trace_commodities=str(row.get('Trace Commodities', '')) if pd.notna(row.get('Trace Commodities')) else None,
                )
                db.add(occurrence)
                
                if (idx + 1) % 100 == 0:
                    db.commit()
                    print(f"Inserted {idx + 1} rows...")
                    
            except Exception as e:
                print(f"Error processing row {idx}: {e}")
                continue
        
        db.commit()
        print(f"✅ Successfully loaded {len(df)} occurrences into database!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    try:
        load_mods_to_db()
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
