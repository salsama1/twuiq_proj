from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict, Literal, Union


class OccurrenceInfo(BaseModel):
    """Schema for occurrence information returned from queries"""
    mods_id: str
    english_name: str
    arabic_name: Optional[str] = None
    major_commodity: str
    longitude: float
    latitude: float
    admin_region: Optional[str] = None
    elevation: Optional[float] = None
    occurrence_type: Optional[str] = None
    exploration_status: Optional[str] = None
    occurrence_importance: Optional[str] = None
    description: Optional[str] = None

    class Config:
        from_attributes = True


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)


class QueryResponse(BaseModel):
    response: str
    occurrences: Optional[List[OccurrenceInfo]] = None


class AgentRequest(BaseModel):
    query: str = Field(..., min_length=1)
    max_steps: int = Field(default=3, ge=1, le=8)


class ToolTraceItem(BaseModel):
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)
    # Optional common metrics
    results_count: Optional[int] = None
    features_count: Optional[int] = None
    rows: Optional[int] = None
    bins: Optional[int] = None
    csv_bytes: Optional[int] = None
    # Error/debug
    error: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class RegionCount(BaseModel):
    admin_region: Optional[str] = None
    count: int


class ImportanceCount(BaseModel):
    occurrence_importance: Optional[str] = None
    count: int


class HeatmapBin(BaseModel):
    lon: float
    lat: float
    count: int


class NearestResult(BaseModel):
    distance_m: Optional[float] = None
    occurrence: OccurrenceInfo


class GeoJSONPointGeometry(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: List[float]  # [lon, lat]


class GeoJSONFeatureProperties(BaseModel):
    id: int
    mods_id: str
    english_name: Optional[str] = None
    arabic_name: Optional[str] = None
    major_commodity: Optional[str] = None
    admin_region: Optional[str] = None
    occurrence_type: Optional[str] = None
    exploration_status: Optional[str] = None
    occurrence_importance: Optional[str] = None


class GeoJSONFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: GeoJSONPointGeometry
    properties: GeoJSONFeatureProperties


class GeoJSONFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: List[GeoJSONFeature]


class AgentArtifacts(BaseModel):
    # Exports
    geojson: Optional[GeoJSONFeatureCollection] = None
    csv: Optional[str] = None
    # Analysis
    stats_by_region: Optional[List[RegionCount]] = None
    importance_breakdown: Optional[List[ImportanceCount]] = None
    heatmap_bins: Optional[List[HeatmapBin]] = None
    # Geo
    nearest_results: Optional[List[NearestResult]] = None
    # Escape hatch for any future artifacts
    extra: Dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    response: str
    tool_trace: List[ToolTraceItem] = Field(default_factory=list)
    occurrences: Optional[List[OccurrenceInfo]] = None
    artifacts: AgentArtifacts = Field(default_factory=AgentArtifacts)
