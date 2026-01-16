export type RasterFormatsResponse = {
  rasterio_available: boolean;
  supported_uploads: string[];
  notes?: string[];
};

export type RasterUploadResponse = {
  job_id: string;
  status_url: string; // /jobs/{id}
  raster_path: string;
};

export async function fetchRasterFormats(baseUrl: string): Promise<RasterFormatsResponse> {
  const b = baseUrl.replace(/\/$/, "");
  const res = await fetch(`${b}/rasters/formats`, { method: "GET" });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} ${res.statusText} @ ${b}/rasters/formats: ${txt}`.trim());
  }
  return (await res.json()) as RasterFormatsResponse;
}

export async function uploadRaster(baseUrl: string, file: File): Promise<RasterUploadResponse> {
  const b = baseUrl.replace(/\/$/, "");
  const fd = new FormData();
  fd.append("file", file, file.name);
  const res = await fetch(`${b}/rasters/upload`, { method: "POST", body: fd });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} ${res.statusText} @ ${b}/rasters/upload: ${txt}`.trim());
  }
  return (await res.json()) as RasterUploadResponse;
}

