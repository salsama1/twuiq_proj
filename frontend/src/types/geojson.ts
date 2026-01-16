/**
 * Lightweight GeoJSON types for app usage.
 * We keep these intentionally permissive and cast where Mapbox GL typings are stricter.
 */
export type GeoJSONGeometry =
  | { type: "Point"; coordinates: [number, number] }
  | { type: "LineString"; coordinates: [number, number][] }
  | { type: "Polygon"; coordinates: [number, number][][] }
  | { type: "MultiPoint"; coordinates: [number, number][] }
  | { type: "MultiLineString"; coordinates: [number, number][][] }
  | { type: "MultiPolygon"; coordinates: [number, number][][][] }
  | { type: string; coordinates?: unknown }; // escape hatch

export type GeoJSONFeature<G extends GeoJSONGeometry = GeoJSONGeometry> = {
  type: "Feature";
  geometry: G;
  properties?: Record<string, unknown> | null;
  id?: string | number;
};

export type GeoJSONFeatureCollection<G extends GeoJSONGeometry = GeoJSONGeometry> = {
  type: "FeatureCollection";
  features: Array<GeoJSONFeature<G>>;
};

