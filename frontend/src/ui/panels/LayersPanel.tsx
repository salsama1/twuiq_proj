import { useEffect, useMemo, useState } from "react";
import { useAppStore } from "../../store/appStore";
import { fetchFileFormats, parseGeofile } from "../../api/files";
import { fetchRasterFormats, uploadRaster } from "../../api/rasters";
import { fetchJob } from "../../api/jobs";
import type { GeoJSONFeatureCollection } from "../../types/geojson";
import type { DatasetLayer } from "../../store/appStore";

/**
 * LayersPanel
 *
 * Responsibilities:
 * - Show datasets currently loaded into the app (mostly from agent artifacts).
 * - Provide per-dataset visualization controls (scatter/heatmap/hexagon, styling, extrusion).
 * - Provide map-level settings (Surface / basemap selection).
 */
export function LayersPanel() {
  const datasets = useAppStore((s) => s.datasets);
  const activeDatasetId = useAppStore((s) => s.activeDatasetId);
  const setActiveDatasetId = useAppStore((s) => s.setActiveDatasetId);
  const setDatasetVisible = useAppStore((s) => s.setDatasetVisible);
  const updateDatasetStyle = useAppStore((s) => s.updateDatasetStyle);
  const config = useAppStore((s) => s.config);
  const upsertDataset = useAppStore((s) => s.upsertDataset);
  const terrainEnabled = useAppStore((s) => s.map.terrainEnabled);
  const setTerrainEnabled = useAppStore((s) => s.map.setTerrainEnabled);
  const terrainSurface = useAppStore((s) => s.map.terrainSurface);
  const setTerrainSurface = useAppStore((s) => s.map.setTerrainSurface);
  const deckAvailable = useAppStore((s) => s.map.deckAvailable);
  const deckError = useAppStore((s) => s.map.deckError);

  const active = useMemo(() => datasets.find((d) => d.id === activeDatasetId) ?? null, [datasets, activeDatasetId]);

  const backendUrl = useMemo(() => config?.backendUrl ?? "", [config]);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const [formats, setFormats] = useState<null | { pure_python: string[]; gdal_optional: string[]; gdal_available: boolean }>(null);

  const [rasterFile, setRasterFile] = useState<File | null>(null);
  const [rasterBusy, setRasterBusy] = useState(false);
  const [rasterMsg, setRasterMsg] = useState<string | null>(null);
  const [rasterFormats, setRasterFormats] = useState<null | { rasterio_available: boolean; supported_uploads: string[] }>(null);

  // Ensure an active dataset is selected for UX consistency (when any dataset exists).
  useEffect(() => {
    if (!activeDatasetId && datasets.length) setActiveDatasetId(datasets[0].id);
  }, [activeDatasetId, datasets, setActiveDatasetId]);

  // Terrain is part of the core map experience; keep it enabled (UI toggle removed).
  useEffect(() => {
    if (!terrainEnabled) setTerrainEnabled(true);
  }, [terrainEnabled, setTerrainEnabled]);

  useEffect(() => {
    // Best-effort: show supported formats in the UI. Ignore errors (backend might not have /files enabled yet).
    void (async () => {
      try {
        const r = await fetchFileFormats(backendUrl);
        setFormats(r);
      } catch {
        setFormats(null);
      }
    })();
  }, [backendUrl]);

  useEffect(() => {
    void (async () => {
      try {
        const r = await fetchRasterFormats(backendUrl);
        setRasterFormats(r);
      } catch {
        setRasterFormats(null);
      }
    })();
  }, [backendUrl]);

  function guessKind(fc: GeoJSONFeatureCollection): DatasetLayer["kind"] {
    const feats: any[] = (fc as any)?.features ?? [];
    let hasPoint = false;
    let hasPoly = false;
    for (const f of feats) {
      const t = f?.geometry?.type;
      if (t === "Point" || t === "MultiPoint") hasPoint = true;
      if (t === "Polygon" || t === "MultiPolygon" || t === "LineString" || t === "MultiLineString") hasPoly = true;
    }
    if (hasPoint && !hasPoly) return "points";
    if (!hasPoint && hasPoly) return "polygon";
    return "mixed";
  }

  function geomToFc(geom: any): GeoJSONFeatureCollection {
    return {
      type: "FeatureCollection",
      features: [{ type: "Feature", geometry: geom, properties: { id: "upload-union" } }],
    };
  }

  const EMPTY_FC: GeoJSONFeatureCollection = useMemo(() => ({ type: "FeatureCollection", features: [] }), []);

  async function upload() {
    if (!uploadFile) return;
    setUploadBusy(true);
    setUploadMsg(null);
    try {
      const parsed = await parseGeofile(backendUrl, uploadFile);
      const id = `upload-${Date.now()}`;
      const fc = parsed.feature_collection;
      const kind = guessKind(fc);

      upsertDataset({
        id,
        name: `Upload → ${parsed.filename ?? uploadFile.name}`,
        kind,
        data: fc,
        visible: true,
        style: {
          pointMode: "scatter",
          color: "#60a5fa",
          opacity: 0.85,
          radius: 5,
          heatmapRadius: 24,
          heatmapIntensity: 1,
          hexRadius: 7000,
          hexElevationScale: 25,
          extrude: false,
          extrudeHeight: 250,
        },
      });

      // Also add the union geometry as an AOI dataset (polygon/line) for context.
      if (parsed.union_geometry) {
        upsertDataset({
          id: `${id}-aoi`,
          name: `Upload → AOI (union)`,
          kind: "polygon",
          data: geomToFc(parsed.union_geometry),
          visible: true,
          style: {
            pointMode: "scatter",
            color: "#f59e0b",
            opacity: 0.35,
            radius: 4,
            heatmapRadius: 24,
            heatmapIntensity: 1,
            hexRadius: 7000,
            hexElevationScale: 25,
            extrude: true,
            extrudeHeight: 500,
          },
        });
      }

      setActiveDatasetId(id);
      setUploadMsg(`Uploaded and parsed: ${parsed.filename ?? uploadFile.name}`);
      setUploadFile(null);
    } catch (e: any) {
      setUploadMsg(`Upload failed: ${e?.message ?? String(e)}`);
    } finally {
      setUploadBusy(false);
    }
  }

  async function uploadTif() {
    if (!rasterFile) return;
    setRasterBusy(true);
    setRasterMsg(null);
    try {
      const up = await uploadRaster(backendUrl, rasterFile);
      setRasterMsg(`Uploaded. Processing... (job: ${up.job_id})`);

      const started = Date.now();
      while (true) {
        const j = await fetchJob(backendUrl, up.job_id);
        if (j.status === "succeeded") {
          const rasterId = up.job_id;
          const base = backendUrl.replace(/\/$/, "");
          const tileUrlTemplate = `${base}/rasters/${encodeURIComponent(rasterId)}/tiles/{z}/{x}/{y}.png`;

          upsertDataset({
            id: `raster-${rasterId}`,
            name: `Raster → ${rasterFile.name}`,
            kind: "raster",
            data: EMPTY_FC,
            raster: { tileUrlTemplate, tileSize: 256 },
            visible: true,
            style: {
              pointMode: "scatter",
              color: "#22c55e",
              opacity: 0.75,
              radius: 5,
              heatmapRadius: 24,
              heatmapIntensity: 1,
              hexRadius: 7000,
              hexElevationScale: 25,
              extrude: false,
              extrudeHeight: 250,
            },
          });

          setActiveDatasetId(`raster-${rasterId}`);
          setRasterMsg("Raster ready (added as a map layer).");
          setRasterFile(null);
          break;
        }
        if (j.status === "failed") {
          throw new Error(j.error || "Raster job failed");
        }
        if (Date.now() - started > 120_000) {
          throw new Error("Timed out waiting for raster processing.");
        }
        await new Promise((r) => setTimeout(r, 1000));
      }
    } catch (e: any) {
      setRasterMsg(`Raster upload failed: ${e?.message ?? String(e)}`);
    } finally {
      setRasterBusy(false);
    }
  }

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div className="panelHeader">
        <div className="panelTitle">Layers</div>
      </div>
      <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 10, overflow: "auto" }}>
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 10 }}>
          <div className="krow" style={{ justifyContent: "space-between" }}>
            <div>
              <div style={{ fontWeight: 650 }}>Map Settings</div>
            </div>
          </div>
          <label style={{ fontSize: 12, marginTop: 10, display: "block" }}>
            <div className="muted">Surface</div>
            <select
              className="input"
              value={terrainSurface}
              onChange={(e) => setTerrainSurface(e.target.value as any)}
            >
              {/* "Original" comes from public/config.json (config.mapbox.style). */}
              <option value="original">Original</option>
              <option value="satellite">Satellite</option>
              <option value="street">Street</option>
            </select>
          </label>
        </div>

        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 10 }}>
          <div style={{ fontWeight: 650 }}>Upload</div>
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
            Upload GeoJSON/KML/GPX/WKT. Parsed features will become a new dataset layer.
          </div>
          {formats && (
            <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
              Formats: <b>{formats.pure_python.join(", ")}</b>
              {formats.gdal_available ? (
                <span> · GDAL enabled</span>
              ) : (
                <span> · GDAL not installed (gpkg/zip optional)</span>
              )}
            </div>
          )}
          <div className="krow" style={{ gap: 8, marginTop: 10 }}>
            <input
              className="input"
              type="file"
              onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
              disabled={uploadBusy}
            />
            <button className="btn btnPrimary" onClick={upload} disabled={!uploadFile || uploadBusy}>
              {uploadBusy ? "Uploading…" : "Upload"}
            </button>
          </div>
          {uploadMsg && (
            <div className="muted" style={{ fontSize: 12, marginTop: 8, whiteSpace: "pre-wrap" }}>
              {uploadMsg}
            </div>
          )}
        </div>

        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 10 }}>
          <div style={{ fontWeight: 650 }}>Upload Raster (GeoTIFF)</div>
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
            Upload a <b>.tif/.tiff</b>. The server will generate XYZ PNG tiles and the map will render it as a raster layer.
          </div>
          {rasterFormats && (
            <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
              rasterio: <b>{rasterFormats.rasterio_available ? "available" : "not installed"}</b> · Supported:{" "}
              <b>{rasterFormats.supported_uploads.join(", ")}</b>
            </div>
          )}
          <div className="krow" style={{ gap: 8, marginTop: 10 }}>
            <input
              className="input"
              type="file"
              accept=".tif,.tiff"
              onChange={(e) => setRasterFile(e.target.files?.[0] ?? null)}
              disabled={rasterBusy}
            />
            <button className="btn btnPrimary" onClick={uploadTif} disabled={!rasterFile || rasterBusy}>
              {rasterBusy ? "Uploading…" : "Upload"}
            </button>
          </div>
          {rasterMsg && (
            <div className="muted" style={{ fontSize: 12, marginTop: 8, whiteSpace: "pre-wrap" }}>
              {rasterMsg}
            </div>
          )}
        </div>

        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 10 }}>
          <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
            Datasets
          </div>
          {datasets.length === 0 && (
            <div className="muted" style={{ fontSize: 13 }}>
              No datasets yet. Ask the agent in Chat.
            </div>
          )}

          {datasets.map((d) => (
            <div
              key={d.id}
              style={{
                border: "1px solid var(--border)",
                borderRadius: 12,
                padding: 10,
                marginBottom: 10,
                background: d.id === activeDatasetId ? "rgba(34,197,94,0.06)" : "rgba(255,255,255,0.02)",
              }}
            >
              <div className="krow" style={{ justifyContent: "space-between" }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 650, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {d.name}
                  </div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {d.kind}
                  </div>
                </div>
                <div className="krow">
                  <button className="btn" onClick={() => setActiveDatasetId(d.id)}>
                    View
                  </button>
                  <input type="checkbox" checked={d.visible} onChange={(e) => setDatasetVisible(d.id, e.target.checked)} />
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 10 }}>
                <label style={{ fontSize: 12 }}>
                  <div className="muted">Point mode</div>
                  <select
                    className="input"
                    value={d.style.pointMode ?? "scatter"}
                    onChange={(e) => updateDatasetStyle(d.id, { pointMode: e.target.value as any })}
                    disabled={d.kind === "raster"}
                  >
                    <option value="scatter">Scatter</option>
                    <option value="heatmap">Heatmap</option>
                    <option value="hexagon" disabled={deckAvailable !== true}>
                      Hexagon (3D)
                    </option>
                  </select>
                </label>
                {deckAvailable !== true && (
                  <div className="muted" style={{ gridColumn: "1 / -1", fontSize: 12 }}>
                    Hexagon (3D) is unavailable. {deckError ?? "Checking WebGL2/deck.gl…"} Use Scatter/Heatmap instead.
                  </div>
                )}
                <label style={{ fontSize: 12 }}>
                  <div className="muted">Color</div>
                  <input
                    className="input"
                    type="color"
                    value={d.style.color}
                    onChange={(e) => updateDatasetStyle(d.id, { color: e.target.value })}
                    style={{ padding: 4, height: 38 }}
                    disabled={d.kind === "raster"}
                  />
                </label>
                <label style={{ fontSize: 12 }}>
                  <div className="muted">Opacity</div>
                  <input
                    className="input"
                    type="range"
                    min={0}
                    max={100}
                    value={Math.round(d.style.opacity * 100)}
                    onChange={(e) => updateDatasetStyle(d.id, { opacity: Number(e.target.value) / 100 })}
                  />
                </label>
                <label style={{ fontSize: 12 }}>
                  <div className="muted">Point radius</div>
                  <input
                    className="input"
                    type="range"
                    min={2}
                    max={14}
                    value={d.style.radius}
                    onChange={(e) => updateDatasetStyle(d.id, { radius: Number(e.target.value) })}
                    disabled={d.kind === "raster" || (d.style.pointMode ?? "scatter") !== "scatter"}
                  />
                </label>
                <label style={{ fontSize: 12 }}>
                  <div className="muted">Heatmap radius</div>
                  <input
                    className="input"
                    type="range"
                    min={5}
                    max={60}
                    value={d.style.heatmapRadius ?? 24}
                    onChange={(e) => updateDatasetStyle(d.id, { heatmapRadius: Number(e.target.value) })}
                    disabled={d.kind === "raster" || (d.style.pointMode ?? "scatter") !== "heatmap"}
                  />
                </label>
                <label style={{ fontSize: 12 }}>
                  <div className="muted">Heatmap intensity</div>
                  <input
                    className="input"
                    type="range"
                    min={0}
                    max={500}
                    value={Math.round((d.style.heatmapIntensity ?? 1) * 100)}
                    onChange={(e) => updateDatasetStyle(d.id, { heatmapIntensity: Number(e.target.value) / 100 })}
                    disabled={d.kind === "raster" || (d.style.pointMode ?? "scatter") !== "heatmap"}
                  />
                </label>
                <label style={{ fontSize: 12 }}>
                  <div className="muted">Hex radius (m)</div>
                  <input
                    className="input"
                    type="range"
                    min={1000}
                    max={25000}
                    step={500}
                    value={d.style.hexRadius ?? 7000}
                    onChange={(e) => updateDatasetStyle(d.id, { hexRadius: Number(e.target.value) })}
                    disabled={d.kind === "raster" || (d.style.pointMode ?? "scatter") !== "hexagon"}
                  />
                </label>
                <label style={{ fontSize: 12 }}>
                  <div className="muted">Hex elevation</div>
                  <input
                    className="input"
                    type="range"
                    min={1}
                    max={120}
                    value={d.style.hexElevationScale ?? 25}
                    onChange={(e) => updateDatasetStyle(d.id, { hexElevationScale: Number(e.target.value) })}
                    disabled={d.kind === "raster" || (d.style.pointMode ?? "scatter") !== "hexagon"}
                  />
                </label>
                <label style={{ fontSize: 12 }}>
                  <div className="muted">Extrude polygons</div>
                  <div className="krow" style={{ justifyContent: "space-between" }}>
                    <input
                      type="checkbox"
                      checked={d.style.extrude}
                      onChange={(e) => updateDatasetStyle(d.id, { extrude: e.target.checked })}
                      disabled={d.kind === "raster"}
                    />
                    <span className="muted" style={{ fontSize: 12 }}>
                      height: {d.style.extrudeHeight}
                    </span>
                  </div>
                  <input
                    className="input"
                    type="range"
                    min={0}
                    max={2000}
                    step={25}
                    value={d.style.extrudeHeight}
                    onChange={(e) => updateDatasetStyle(d.id, { extrudeHeight: Number(e.target.value) })}
                    disabled={d.kind === "raster" || !d.style.extrude}
                  />
                </label>
              </div>
            </div>
          ))}
        </div>

        {active && (
          <div className="muted" style={{ fontSize: 12 }}>
            Active dataset: <b style={{ color: "var(--text)" }}>{active.name}</b>
          </div>
        )}
      </div>
    </div>
  );
}

