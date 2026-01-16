import type { GeoJSONFeatureCollection } from "./geojson";

/**
 * Shared API types between frontend and backend.
 * These types reflect the shapes consumed by the UI (chat, table, map artifacts).
 */
export type OccurrenceInfo = {
  mods_id: string;
  english_name: string;
  arabic_name?: string | null;
  major_commodity: string;
  longitude: number;
  latitude: number;
  admin_region?: string | null;
  elevation?: number | null;
  occurrence_type?: string | null;
  exploration_status?: string | null;
  occurrence_importance?: string | null;
  description?: string | null;
};

export type ToolTraceItem = {
  tool: string;
  args?: Record<string, unknown>;
  results_count?: number | null;
  features_count?: number | null;
  rows?: number | null;
  bins?: number | null;
  csv_bytes?: number | null;
  error?: string | null;
  raw?: Record<string, unknown> | null;
};

export type WorkflowStep = {
  action: string;
  args: Record<string, unknown>;
  why?: string | null;
};

export type AgentArtifacts = {
  geojson?: GeoJSONFeatureCollection | null;
  spatial_geojson?: GeoJSONFeatureCollection | null;
  spatial_buffer_geometry?: Record<string, unknown> | null;
  csv?: string | null;
  stats_by_region?: { admin_region: string | null; count: number }[] | null;
  stats_by_type?: { occurrence_type: string | null; count: number }[] | null;
  stats_region_by_type?: { admin_region: string | null; occurrence_type: string | null; count: number }[] | null;
  importance_breakdown?: { occurrence_importance: string | null; count: number }[] | null;
  heatmap_bins?: { lon: number; lat: number; count: number }[] | null;
  nearest_results?: any[] | null;
  extra?: Record<string, unknown>;
};

export type WorkflowResponse = {
  response: string;
  plan: WorkflowStep[];
  tool_trace: ToolTraceItem[];
  occurrences?: OccurrenceInfo[] | null;
  artifacts: AgentArtifacts;
  session_id?: string | null;
};

// Simple agent endpoint (automatic routing; no user-visible LLM toggle)
export type AgentRequest = {
  query: string;
  max_steps?: number;
  session_id?: string | null;
};

export type AgentResponse = {
  response: string;
  tool_trace: ToolTraceItem[];
  occurrences?: OccurrenceInfo[] | null;
  artifacts: AgentArtifacts;
  session_id?: string | null;
};

export type AdvancedSearchRequest = {
  commodities?: string[];
  regions?: string[];
  occurrence_types?: string[];
  exploration_statuses?: string[];
  importance?: string[];
  q?: string;
  bbox?: [number, number, number, number]; // [min_lon, min_lat, max_lon, max_lat]
  polygon?: Record<string, unknown>;
  limit?: number;
  offset?: number;
  return_geojson?: boolean;
};

export type AdvancedSearchResponse = {
  total: number;
  occurrences: OccurrenceInfo[];
  geojson?: GeoJSONFeatureCollection | null;
  applied: Record<string, unknown>;
};

