import { httpJson } from "./http";
import type { GeoJSONFeatureCollection } from "../types/geojson";

export type FilesFormatsResponse = {
  pure_python: string[];
  gdal_optional: string[];
  gdal_available: boolean;
  notes?: string[];
};

export type FilesParseResponse = {
  type: "parsed_file";
  filename?: string | null;
  content_type?: string | null;
  feature_collection: GeoJSONFeatureCollection;
  union_geometry: Record<string, unknown>;
};

export async function fetchFileFormats(baseUrl: string): Promise<FilesFormatsResponse> {
  const b = baseUrl.replace(/\/$/, "");
  return await httpJson<FilesFormatsResponse>(`${b}/files/formats`, { method: "GET" });
}

export async function parseGeofile(baseUrl: string, file: File): Promise<FilesParseResponse> {
  const b = baseUrl.replace(/\/$/, "");
  const fd = new FormData();
  fd.append("file", file, file.name);
  // Use plain fetch for multipart.
  const res = await fetch(`${b}/files/parse`, { method: "POST", body: fd });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} ${res.statusText} @ ${b}/files/parse: ${txt}`.trim());
  }
  return (await res.json()) as FilesParseResponse;
}

