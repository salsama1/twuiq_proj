import type { AppConfig } from "./types";

/**
 * Attempts to fetch and parse JSON from a given path.
 * Returns null on any failure (network error, invalid JSON, non-2xx).
 */
async function tryFetchJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(path, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

/**
 * Loads runtime app configuration.
 *
 * Expected flow:
 * - `public/config.json` exists locally (gitignored) and contains real values.
 * - If missing, we fall back to `public/config.example.json` so the UI can render,
 *   and we return a "hint" message to guide the user.
 */
export async function loadAppConfig(): Promise<{
  config: AppConfig | null;
  hint: string | null;
}> {
  // We intentionally do NOT ship a real token in the repo.
  // Users should create `public/config.json` locally (not committed) by copying `config.example.json`.
  const config = await tryFetchJson<AppConfig>("/config.json");
  if (config) return { config, hint: null };

  // Fall back to example so the UI can show a helpful "how to configure" banner.
  const example = await tryFetchJson<AppConfig>("/config.example.json");
  return {
    config: example,
    hint:
      "Missing /config.json. Copy public/config.example.json to public/config.json and set your Mapbox public token + backendUrl.",
  };
}

