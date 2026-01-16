import type { AdvancedSearchRequest, AdvancedSearchResponse } from "../types/api";
import { httpJson } from "./http";

/**
 * Optional advanced server-side search.
 * Not currently wired into the UI, but kept for future filtering panels.
 */
export async function advancedMods(
  baseUrl: string,
  req: AdvancedSearchRequest
): Promise<AdvancedSearchResponse> {
  return await httpJson<AdvancedSearchResponse>(`${baseUrl}/advanced/mods`, {
    method: "POST",
    json: {
      ...req,
      limit: req.limit ?? 1000,
      offset: req.offset ?? 0,
      return_geojson: req.return_geojson ?? true,
    },
  });
}

