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
    session_id: Optional[str] = None


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
    # Spatial ops
    spatial_geojson: Optional[GeoJSONFeatureCollection] = None
    spatial_total: Optional[int] = None
    spatial_buffer_geometry: Optional[Dict[str, Any]] = None
    spatial_nearest: Optional[List[Dict[str, Any]]] = None
    # Chart-ready payloads (Vega-Lite specs + data)
    charts: Optional[List[Dict[str, Any]]] = None
    # Human-summary metadata (for evaluation + safety)
    summary_source: Optional[Literal["llm", "fallback", "offline"]] = None
    summary_validated: Optional[bool] = None
    summary_violations: Optional[List[str]] = None
    # Escape hatch for any future artifacts
    extra: Dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    response: str
    tool_trace: List[ToolTraceItem] = Field(default_factory=list)
    occurrences: Optional[List[OccurrenceInfo]] = None
    artifacts: AgentArtifacts = Field(default_factory=AgentArtifacts)
    session_id: Optional[str] = None


class WorkflowStep(BaseModel):
    action: str
    args: Dict[str, Any] = Field(default_factory=dict)
    why: Optional[str] = None


class WorkflowRequest(BaseModel):
    query: str = Field(..., min_length=1)
    max_steps: int = Field(default=6, ge=1, le=12)
    use_llm: bool = True
    session_id: Optional[str] = None


class WorkflowResponse(BaseModel):
    response: str
    plan: List[WorkflowStep] = Field(default_factory=list)
    tool_trace: List[ToolTraceItem] = Field(default_factory=list)
    occurrences: Optional[List[OccurrenceInfo]] = None
    artifacts: AgentArtifacts = Field(default_factory=AgentArtifacts)
    session_id: Optional[str] = None


class AdvancedSearchRequest(BaseModel):
    """
    Advanced query interface (POST) for geospatial scientists and QGIS workflows.
    Supports multi-value filters and geometry filters.
    """

    # Multi-value filters
    commodities: Optional[List[str]] = None
    regions: Optional[List[str]] = None
    occurrence_types: Optional[List[str]] = None
    exploration_statuses: Optional[List[str]] = None
    importance: Optional[List[str]] = None

    # Free-text (matches name/commodity/region/type/status)
    q: Optional[str] = None

    # Geometry filters (WGS84)
    # bbox = [min_lon, min_lat, max_lon, max_lat]
    bbox: Optional[List[float]] = None
    # GeoJSON geometry object (Polygon or MultiPolygon recommended)
    polygon: Optional[Dict[str, Any]] = None

    # Pagination
    limit: int = Field(default=500, ge=1, le=5000)
    offset: int = Field(default=0, ge=0, le=500000)

    # Response shape
    return_geojson: bool = True


class AdvancedSearchResponse(BaseModel):
    total: int
    occurrences: List[OccurrenceInfo]
    geojson: Optional[GeoJSONFeatureCollection] = None
    applied: Dict[str, Any] = Field(default_factory=dict)


class SpatialQueryRequest(BaseModel):
    """
    Spatial operations for geospatial specialists (POST).
    Supply any GeoJSON geometry (Point/LineString/Polygon/Multi*).
    """

    # GeoJSON geometry object
    geometry: Dict[str, Any]

    # Spatial op
    op: Literal["intersects", "dwithin"] = "intersects"
    # Only used for dwithin (meters, via WebMercator transform)
    distance_m: Optional[float] = Field(default=None, ge=0)

    # Optional attribute filters (single values; same semantics as other endpoints)
    commodity: Optional[str] = None
    region: Optional[str] = None
    occurrence_type: Optional[str] = None
    exploration_status: Optional[str] = None

    # Pagination
    limit: int = Field(default=500, ge=1, le=5000)
    offset: int = Field(default=0, ge=0, le=500000)

    # Response shape
    return_geojson: bool = True


class SpatialQueryResponse(BaseModel):
    total: int
    occurrences: List[OccurrenceInfo]
    geojson: Optional[GeoJSONFeatureCollection] = None
    applied: Dict[str, Any] = Field(default_factory=dict)


class SpatialBufferRequest(BaseModel):
    """
    Build a buffer polygon around any GeoJSON geometry.
    """

    geometry: Dict[str, Any]
    distance_m: float = Field(..., ge=0)


class SpatialBufferResponse(BaseModel):
    """
    Returns the buffered geometry as GeoJSON (EPSG:4326).
    """

    geojson_geometry: Dict[str, Any]
    applied: Dict[str, Any] = Field(default_factory=dict)


class SpatialNearestRequest(BaseModel):
    """
    Nearest MODS points to an arbitrary GeoJSON geometry.
    """

    geometry: Dict[str, Any]
    limit: int = Field(default=25, ge=1, le=500)
    commodity: Optional[str] = None
    region: Optional[str] = None
    occurrence_type: Optional[str] = None
    exploration_status: Optional[str] = None


class SpatialNearestResponse(BaseModel):
    total_returned: int
    results: List[Dict[str, Any]]
    applied: Dict[str, Any] = Field(default_factory=dict)


class SpatialOverlayRequest(BaseModel):
    """
    Vector overlay operations on arbitrary GeoJSON geometries (EPSG:4326).
    """

    op: Literal["union", "intersection", "difference", "symmetric_difference"] = "intersection"
    a: Dict[str, Any]
    b: Dict[str, Any]


class SpatialOverlayResponse(BaseModel):
    geojson_geometry: Dict[str, Any]
    applied: Dict[str, Any] = Field(default_factory=dict)


class SpatialDissolveRequest(BaseModel):
    """
    Dissolve/merge GeoJSON FeatureCollection by a property key.
    """

    feature_collection: Dict[str, Any]
    by_property: str = Field(..., min_length=1)
    max_features: int = Field(default=5000, ge=1, le=50000)


class SpatialDissolveResponse(BaseModel):
    feature_collection: Dict[str, Any]
    applied: Dict[str, Any] = Field(default_factory=dict)


class SpatialJoinCountsRequest(BaseModel):
    """
    Spatial join: count MODS points within/intersecting each polygon feature.
    """

    feature_collection: Dict[str, Any]
    predicate: Literal["intersects", "contains"] = "intersects"
    id_property: str = Field(default="id", min_length=1)
    max_features: int = Field(default=200, ge=1, le=5000)


class SpatialJoinCountsResponse(BaseModel):
    feature_collection: Dict[str, Any]
    applied: Dict[str, Any] = Field(default_factory=dict)


class SpatialJoinNearestRequest(BaseModel):
    """
    Spatial join: for each input feature, find the nearest MODS point and distance.
    """

    feature_collection: Dict[str, Any]
    id_property: str = Field(default="id", min_length=1)
    limit_features: int = Field(default=200, ge=1, le=5000)


class SpatialJoinNearestResponse(BaseModel):
    features: List[Dict[str, Any]]
    applied: Dict[str, Any] = Field(default_factory=dict)


class RasterZonalStatsRequest(BaseModel):
    geometry: Dict[str, Any]
    band: int = Field(default=1, ge=1)


class RasterZonalStatsResponse(BaseModel):
    raster_id: str
    band: int
    stats: Dict[str, Any]
