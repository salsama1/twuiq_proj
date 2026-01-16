"""
=============================================================================
GEOSPATIAL RAG - TOOL 2: 2D VISUALIZER (FIXED)
=============================================================================
Prepares data for Leaflet.js 2D map visualization
=============================================================================
"""

import logging
from typing import Dict, Any, List, Optional
import json

from database.postgis_client import get_postgis_client

logger = logging.getLogger(__name__)


class Visualizer2D:
    """Prepares geospatial data for 2D Leaflet map visualization."""
    
    def __init__(self):
        self.db = get_postgis_client()
    
    def _validate_and_fix_coordinates(self, lat: float, lon: float) -> tuple:
        """
        Validate coordinates and swap if they appear reversed.
        Saudi Arabia bounds: lat 16-32, lon 34-56
        """
        if lat is None or lon is None:
            return None, None
        
        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            return None, None
        
        # Check if coordinates are valid for Saudi Arabia region
        lat_valid = 10 <= lat <= 35
        lon_valid = 30 <= lon <= 60
        
        if lat_valid and lon_valid:
            return lat, lon
        
        # Check if swapped
        lat_as_lon = 30 <= lat <= 60
        lon_as_lat = 10 <= lon <= 35
        
        if lat_as_lon and lon_as_lat:
            logger.debug(f"Swapping coordinates: ({lat}, {lon}) -> ({lon}, {lat})")
            return lon, lat
        
        # Return as-is if we can't determine
        return lat, lon
    
    def to_geojson(
        self,
        data: List[Dict[str, Any]],
        lat_field: str = "latitude",
        lon_field: str = "longitude",
        properties_exclude: List[str] = None
    ) -> Dict[str, Any]:
        """
        Convert query results to GeoJSON FeatureCollection.
        
        Args:
            data: List of dictionaries with lat/lon
            lat_field: Name of latitude field
            lon_field: Name of longitude field
            properties_exclude: Fields to exclude from properties
            
        Returns:
            GeoJSON FeatureCollection
        """
        if properties_exclude is None:
            properties_exclude = [lat_field, lon_field, "geom"]
        
        features = []
        for row in data:
            lat = row.get(lat_field)
            lon = row.get(lon_field)
            
            # Validate and potentially swap coordinates
            lat, lon = self._validate_and_fix_coordinates(lat, lon)
            
            if lat is None or lon is None:
                continue
            
            # Build properties (everything except geometry fields)
            properties = {
                k: v for k, v in row.items()
                if k not in properties_exclude and v is not None
            }
            
            # GeoJSON uses [longitude, latitude] order!
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat]  # [X, Y] = [lon, lat]
                },
                "properties": properties
            }
            features.append(feature)
        
        return {
            "type": "FeatureCollection",
            "features": features
        }
    
    def get_bounds(self, geojson: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate bounding box from GeoJSON.
        
        Returns:
            Dictionary with min_lat, max_lat, min_lon, max_lon
        """
        if not geojson.get("features"):
            return None
        
        lats = []
        lons = []
        
        for feature in geojson["features"]:
            coords = feature.get("geometry", {}).get("coordinates", [])
            if len(coords) >= 2:
                lons.append(coords[0])  # X = longitude
                lats.append(coords[1])  # Y = latitude
        
        if not lats or not lons:
            return None
        
        return {
            "min_lat": min(lats),
            "max_lat": max(lats),
            "min_lon": min(lons),
            "max_lon": max(lons),
            "center_lat": sum(lats) / len(lats),
            "center_lon": sum(lons) / len(lons)
        }
    
    def create_layer_config(
        self,
        geojson: Dict[str, Any],
        layer_name: str,
        style: Optional[Dict[str, Any]] = None,
        popup_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create complete layer configuration for frontend.
        """
        bounds = self.get_bounds(geojson)
        
        # Default styling
        default_style = {
            "color": "#3388ff",
            "fillColor": "#3388ff",
            "fillOpacity": 0.6,
            "radius": 8,
            "weight": 2
        }
        
        if style:
            default_style.update(style)
        
        # Infer popup fields if not provided
        if popup_fields is None and geojson.get("features"):
            first_props = geojson["features"][0].get("properties", {})
            popup_fields = list(first_props.keys())[:5]
        
        return {
            "layer_name": layer_name,
            "geojson": geojson,
            "bounds": bounds,
            "feature_count": len(geojson.get("features", [])),
            "style": default_style,
            "popup_fields": popup_fields,
            "layer_type": "point"
        }
    
    def prepare_visualization(
        self,
        data: List[Dict[str, Any]],
        layer_name: str = "Query Results",
        color: str = "#3388ff",
        popup_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Main method to prepare complete visualization data.
        """
        geojson = self.to_geojson(data)
        
        style = {
            "color": color,
            "fillColor": color
        }
        
        config = self.create_layer_config(
            geojson=geojson,
            layer_name=layer_name,
            style=style,
            popup_fields=popup_fields
        )
        
        return config
    
    def create_heatmap_data(
        self,
        data: List[Dict[str, Any]],
        lat_field: str = "latitude",
        lon_field: str = "longitude",
        intensity_field: Optional[str] = None
    ) -> List[List[float]]:
        """
        Prepare data for Leaflet.heat heatmap.
        
        Returns:
            List of [lat, lon, intensity] for heatmap
        """
        heatmap_data = []
        
        for row in data:
            lat = row.get(lat_field)
            lon = row.get(lon_field)
            
            # Validate and fix coordinates
            lat, lon = self._validate_and_fix_coordinates(lat, lon)
            
            if lat is None or lon is None:
                continue
            
            if intensity_field and intensity_field in row:
                intensity = float(row[intensity_field]) if row[intensity_field] else 1.0
            else:
                intensity = 1.0
            
            # Heatmap uses [lat, lon, intensity]
            heatmap_data.append([lat, lon, intensity])
        
        return heatmap_data
    
    def create_cluster_config(
        self,
        data: List[Dict[str, Any]],
        layer_name: str = "Clustered Points"
    ) -> Dict[str, Any]:
        """
        Prepare data for Leaflet.markercluster.
        """
        geojson = self.to_geojson(data)
        bounds = self.get_bounds(geojson)
        
        return {
            "layer_name": layer_name,
            "geojson": geojson,
            "bounds": bounds,
            "feature_count": len(geojson.get("features", [])),
            "cluster_options": {
                "spiderfyOnMaxZoom": True,
                "showCoverageOnHover": True,
                "zoomToBoundsOnClick": True,
                "maxClusterRadius": 50
            }
        }


# Global instance
_visualizer_2d: Optional[Visualizer2D] = None


def get_visualizer_2d() -> Visualizer2D:
    """Get or create the global 2D visualizer."""
    global _visualizer_2d
    if _visualizer_2d is None:
        _visualizer_2d = Visualizer2D()
    return _visualizer_2d