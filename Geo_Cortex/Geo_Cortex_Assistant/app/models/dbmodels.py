from app.database import Base
from sqlalchemy import Column, Integer, String, Float, Text
from geoalchemy2 import Geography


class MODSOccurrence(Base):
    """Class to represent MODS occurrences from CSV"""
    __tablename__ = 'mods_occurrences'
    
    id = Column(Integer, primary_key=True, index=True)
    mods_id = Column(String, unique=True, index=True)  # MODS 1909, etc.
    english_name = Column(String, index=True)
    arabic_name = Column(String)
    library_reference = Column(Text)
    major_commodity = Column(String, index=True)
    longitude = Column(Float, index=True)
    latitude = Column(Float, index=True)
    # Geographic point stored as PostGIS geography (WGS84)
    geom = Column(Geography(geometry_type="POINT", srid=4326), index=True)
    quadrangle = Column(String)
    admin_region = Column(String, index=True)
    elevation = Column(Float)
    occurrence_type = Column(String, index=True)  # Metallic, Non Metallic
    input_date = Column(String)
    last_update = Column(String)
    position_origin = Column(String)
    exploration_status = Column(String, index=True)
    security_status = Column(String)
    occurrence_importance = Column(String, index=True)
    occurrence_status = Column(String, index=True)
    ancient_workings = Column(String)
    geochemical_exploration = Column(String)
    geophysical_exploration = Column(String)
    mapping_exploration = Column(Text)
    exploration_data = Column(Text)
    structural_province = Column(String)
    regional_structure = Column(String)
    geologic_group = Column(String)
    geologic_formation = Column(String)
    host_rocks = Column(Text)
    country_rocks = Column(Text)
    geology = Column(String)
    mineralization_control = Column(String)
    alteration = Column(String)
    mineralization_morphology = Column(String)
    minor_commodities = Column(Text)
    trace_commodities = Column(Text)
