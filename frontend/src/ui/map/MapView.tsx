import { useEffect, useMemo, useRef } from "react";
import mapboxgl, { type MapMouseEvent, Map as MapboxMap } from "mapbox-gl";
import { useAppStore, type DatasetLayer } from "../../store/appStore";
import type { GeoJSONFeatureCollection } from "../../types/geojson";

/**
 * MapView (Mapbox GL JS + optional deck.gl overlay)
 *
 * Responsibilities:
 * - Initialize a single Mapbox map instance (stable across React renders).
 * - Render datasets as Mapbox layers (scatter + heatmap) and deck.gl hexagon aggregation.
 * - Handle interactions (hover tooltip, click selection) and sync with global store.
 * - Support style switching ("Surface") and keep map responsive to panel resizing.
 */
type MapboxAny = any;

const SOURCE_ID_PREFIX = "gc-src:";
const LAYER_ID_PREFIX = "gc-lyr:";

function supportsWebGL2Runtime(): boolean {
  // NOTE: Don't probe WebGL2 on Mapbox's own canvas. Mapbox creates the context first,
  // and subsequent `getContext("webgl2")` calls will often return null even when WebGL2 is available.
  try {
    const c = document.createElement("canvas");
    return !!c.getContext("webgl2");
  } catch {
    return false;
  }
}

function mapIsUsingWebGL2(map: MapboxMap): boolean {
  try {
    const gl = (map as any)?.painter?.context?.gl;
    // In some browsers/environments, `instanceof WebGL2RenderingContext` can be unreliable across realms;
    // fall back to constructor name as a best-effort signal.
    if (typeof WebGL2RenderingContext !== "undefined" && gl instanceof WebGL2RenderingContext) return true;
    const name = gl?.constructor?.name ?? "";
    return String(name).toLowerCase().includes("webgl2");
  } catch {
    return false;
  }
}

function computePointBbox(fc: GeoJSONFeatureCollection): [[number, number], [number, number]] | null {
  const feats: any[] = (fc as any)?.features ?? [];
  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity;
  let any = false;
  for (const f of feats) {
    const g = f?.geometry;
    if (!g) continue;
    if (g.type === "Point" && Array.isArray(g.coordinates)) {
      const x = Number(g.coordinates[0]);
      const y = Number(g.coordinates[1]);
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
      any = true;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    } else if (g.type === "MultiPoint" && Array.isArray(g.coordinates)) {
      for (const c of g.coordinates) {
        if (!Array.isArray(c)) continue;
        const x = Number(c[0]);
        const y = Number(c[1]);
        if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
        any = true;
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x);
        maxY = Math.max(maxY, y);
      }
    }
  }
  if (!any) return null;
  return [
    [minX, minY],
    [maxX, maxY],
  ];
}

function ensureSource(map: MapboxMap, id: string, data: GeoJSONFeatureCollection) {
  const existing = map.getSource(id) as MapboxAny | undefined;
  if (!existing) {
    // Mapbox typings expect official geojson types; our app uses a lightweight internal type.
    map.addSource(id, { type: "geojson", data: data as unknown as MapboxAny });
    return;
  }
  existing.setData(data as unknown as MapboxAny);
}

function setLayerVisibility(map: MapboxMap, layerId: string, visible: boolean) {
  if (!map.getLayer(layerId)) return;
  map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
}

function ensureDemAndSky(map: MapboxMap, terrainEnabled: boolean) {
  // Adds Mapbox Terrain DEM + sky layer; safe to call multiple times (checks for existence).
  if (!map.getSource("mapbox-dem")) {
    map.addSource("mapbox-dem", {
      type: "raster-dem",
      url: "mapbox://mapbox.mapbox-terrain-dem-v1",
      tileSize: 512,
      maxzoom: 14,
    } as any);
  }
  try {
    if (terrainEnabled) map.setTerrain({ source: "mapbox-dem", exaggeration: 1.2 } as any);
    else map.setTerrain(null as any);
  } catch {
    // ignore
  }
  if (!map.getLayer("sky")) {
    map.addLayer({
      id: "sky",
      type: "sky",
      paint: { "sky-type": "atmosphere", "sky-atmosphere-sun-intensity": 10 },
    } as any);
  }
}

function applyDatasetsToMap(map: MapboxMap, datasets: DatasetLayer[]) {
  // Upsert per-dataset sources + layers and toggle visibility based on each dataset style.
  datasets.forEach((d) => {
    // --- RASTERS (Mapbox raster tile layer) ---
    if (d.kind === "raster" && d.raster?.tileUrlTemplate) {
      const rasterSrcId = `${SOURCE_ID_PREFIX}${d.id}:raster`;
      const rasterLayerId = `${LAYER_ID_PREFIX}${d.id}:raster`;

      if (!map.getSource(rasterSrcId)) {
        map.addSource(rasterSrcId, {
          type: "raster",
          tiles: [d.raster.tileUrlTemplate],
          tileSize: d.raster.tileSize ?? 256,
        } as any);
      }

      if (!map.getLayer(rasterLayerId)) {
        map.addLayer({
          id: rasterLayerId,
          type: "raster",
          source: rasterSrcId,
          paint: { "raster-opacity": Math.min(1, Math.max(0, d.style.opacity)) },
        } as any);
      } else {
        map.setPaintProperty(rasterLayerId, "raster-opacity", Math.min(1, Math.max(0, d.style.opacity)));
      }

      setLayerVisibility(map, rasterLayerId, d.visible);
      return;
    }

    const srcId = `${SOURCE_ID_PREFIX}${d.id}`;
    ensureSource(map, srcId, d.data);

    const pointMode = d.style.pointMode ?? "scatter";

    // --- POLYGONS / LINES (Mapbox native) ---
    const polyFillId = `${LAYER_ID_PREFIX}${d.id}:polyfill`;
    const polyExtrudeId = `${LAYER_ID_PREFIX}${d.id}:polyextrude`;
    const polyOutlineId = `${LAYER_ID_PREFIX}${d.id}:polyoutline`;
    const lineId = `${LAYER_ID_PREFIX}${d.id}:lines`;

    // Fill (2D)
    if (!map.getLayer(polyFillId)) {
      map.addLayer({
        id: polyFillId,
        type: "fill",
        source: srcId,
        filter: ["any", ["==", ["geometry-type"], "Polygon"], ["==", ["geometry-type"], "MultiPolygon"]],
        paint: {
          "fill-color": d.style.color,
          "fill-opacity": Math.min(0.65, d.style.opacity),
        },
      } as any);
    } else {
      map.setPaintProperty(polyFillId, "fill-color", d.style.color);
      map.setPaintProperty(polyFillId, "fill-opacity", Math.min(0.65, d.style.opacity));
    }
    setLayerVisibility(map, polyFillId, d.visible && !d.style.extrude);

    // Extrusion (3D)
    if (!map.getLayer(polyExtrudeId)) {
      map.addLayer({
        id: polyExtrudeId,
        type: "fill-extrusion",
        source: srcId,
        filter: ["any", ["==", ["geometry-type"], "Polygon"], ["==", ["geometry-type"], "MultiPolygon"]],
        paint: {
          "fill-extrusion-color": d.style.color,
          "fill-extrusion-opacity": Math.min(0.6, d.style.opacity),
          "fill-extrusion-height": d.style.extrudeHeight,
          "fill-extrusion-base": 0,
        },
      } as any);
    } else {
      map.setPaintProperty(polyExtrudeId, "fill-extrusion-color", d.style.color);
      map.setPaintProperty(polyExtrudeId, "fill-extrusion-opacity", Math.min(0.6, d.style.opacity));
      map.setPaintProperty(polyExtrudeId, "fill-extrusion-height", d.style.extrudeHeight);
    }
    setLayerVisibility(map, polyExtrudeId, d.visible && !!d.style.extrude);

    // Polygon outline
    if (!map.getLayer(polyOutlineId)) {
      map.addLayer({
        id: polyOutlineId,
        type: "line",
        source: srcId,
        filter: ["any", ["==", ["geometry-type"], "Polygon"], ["==", ["geometry-type"], "MultiPolygon"]],
        paint: {
          "line-color": d.style.color,
          "line-opacity": Math.min(0.9, d.style.opacity),
          "line-width": 2,
        },
      } as any);
    } else {
      map.setPaintProperty(polyOutlineId, "line-color", d.style.color);
      map.setPaintProperty(polyOutlineId, "line-opacity", Math.min(0.9, d.style.opacity));
    }
    setLayerVisibility(map, polyOutlineId, d.visible);

    // LineStrings
    if (!map.getLayer(lineId)) {
      map.addLayer({
        id: lineId,
        type: "line",
        source: srcId,
        filter: ["any", ["==", ["geometry-type"], "LineString"], ["==", ["geometry-type"], "MultiLineString"]],
        paint: {
          "line-color": d.style.color,
          "line-opacity": Math.min(0.9, d.style.opacity),
          "line-width": 3,
        },
      } as any);
    } else {
      map.setPaintProperty(lineId, "line-color", d.style.color);
      map.setPaintProperty(lineId, "line-opacity", Math.min(0.9, d.style.opacity));
    }
    setLayerVisibility(map, lineId, d.visible);

    const pointLayerId = `${LAYER_ID_PREFIX}${d.id}:points`;
    if (!map.getLayer(pointLayerId)) {
      map.addLayer({
        id: pointLayerId,
        type: "circle",
        source: srcId,
        filter: ["==", ["geometry-type"], "Point"],
        paint: {
          "circle-radius": d.style.radius,
          "circle-color": d.style.color,
          "circle-opacity": d.style.opacity,
          "circle-stroke-width": 1,
          "circle-stroke-color": "rgba(255,255,255,0.25)",
        },
      } as any);
    } else {
      map.setPaintProperty(pointLayerId, "circle-radius", d.style.radius);
      map.setPaintProperty(pointLayerId, "circle-color", d.style.color);
      map.setPaintProperty(pointLayerId, "circle-opacity", d.style.opacity);
    }
    setLayerVisibility(map, pointLayerId, d.visible && pointMode === "scatter");

    const selLayerId = `${LAYER_ID_PREFIX}${d.id}:selected`;
    if (!map.getLayer(selLayerId)) {
      map.addLayer({
        id: selLayerId,
        type: "circle",
        source: srcId,
        filter: ["all", ["==", ["geometry-type"], "Point"], ["==", ["get", "id"], -999999]],
        paint: {
          "circle-radius": ["+", d.style.radius, 3],
          "circle-color": "#ffffff",
          "circle-opacity": 0.95,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#22c55e",
        },
      } as any);
    }
    setLayerVisibility(map, selLayerId, d.visible && pointMode === "scatter");

    const heatLayerId = `${LAYER_ID_PREFIX}${d.id}:heatmap`;
    if (!map.getLayer(heatLayerId)) {
      map.addLayer({
        id: heatLayerId,
        type: "heatmap",
        source: srcId,
        filter: ["==", ["geometry-type"], "Point"],
        paint: {
          "heatmap-weight": 1,
          "heatmap-intensity": d.style.heatmapIntensity ?? 1.0,
          "heatmap-radius": d.style.heatmapRadius ?? 24,
          "heatmap-opacity": Math.min(0.9, d.style.opacity),
          "heatmap-color": [
            "interpolate",
            ["linear"],
            ["heatmap-density"],
            0,
            "rgba(0,0,0,0)",
            0.15,
            "rgba(59,130,246,0.35)",
            0.35,
            "rgba(34,197,94,0.55)",
            0.65,
            "rgba(245,158,11,0.7)",
            1,
            "rgba(239,68,68,0.85)",
          ],
        },
      } as any);
    } else {
      map.setPaintProperty(heatLayerId, "heatmap-intensity", d.style.heatmapIntensity ?? 1.0);
      map.setPaintProperty(heatLayerId, "heatmap-radius", d.style.heatmapRadius ?? 24);
      map.setPaintProperty(heatLayerId, "heatmap-opacity", Math.min(0.9, d.style.opacity));
    }
    setLayerVisibility(map, heatLayerId, d.visible && pointMode === "heatmap");
  });
}

export function MapView() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapboxMap | null>(null);
  const popupRef = useRef<mapboxgl.Popup | null>(null);
  const datasetsRef = useRef<DatasetLayer[]>([]);
  const lastFitKeyRef = useRef<string>("");
  const deckRef = useRef<any | null>(null);
  const deckEnabledRef = useRef<boolean>(false);

  const config = useAppStore((s) => s.config);
  const datasets = useAppStore((s) => s.datasets);
  const terrainEnabled = useAppStore((s) => s.map.terrainEnabled);
  const terrainSurface = useAppStore((s) => s.map.terrainSurface);
  const selectedFeatureId = useAppStore((s) => s.map.selectedFeatureId);
  const setSelectedFeatureId = useAppStore((s) => s.map.setSelectedFeatureId);
  const setDeckAvailable = useAppStore((s) => s.map.setDeckAvailable);
  const setDeckError = useAppStore((s) => s.map.setDeckError);

  // Surface selection controls the basemap style. "Original" comes from config.
  const styleUrl = useMemo(() => {
    if (terrainSurface === "original") {
      return config?.mapbox?.style ?? "mapbox://styles/mapbox/dark-v11";
    }
    if (terrainSurface === "satellite") {
      return "mapbox://styles/mapbox/satellite-streets-v12";
    }
    return "mapbox://styles/mapbox/streets-v12";
  }, [terrainSurface, config]);

  // Keep latest datasets available to event handlers without remounting the map.
  useEffect(() => {
    datasetsRef.current = datasets;
  }, [datasets]);

  // Make Mapbox responsive to panel resizing (chat collapse/expand, table/layers drag, window resize).
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    let raf = 0;
    const ro = new ResizeObserver(() => {
      const map = mapRef.current;
      if (!map) return;
      if (raf) cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        try {
          map.resize();
        } catch {
          // ignore
        }
      });
    });

    ro.observe(el);
    return () => {
      if (raf) cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  // Create map ONCE.
  useEffect(() => {
    if (!containerRef.current) return;
    if (!config?.mapbox?.token || config.mapbox.token.includes("PASTE_")) return;
    if (mapRef.current) return;

    mapboxgl.accessToken = config.mapbox.token;
    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: styleUrl,
      center: [45.0, 24.0],
      zoom: 4.3,
      pitch: 45,
      bearing: 0,
      attributionControl: false,
    });

    map.addControl(new mapboxgl.NavigationControl({ visualizePitch: true }), "bottom-right");
    map.addControl(new mapboxgl.AttributionControl({ compact: true }), "bottom-left");

    // Determine deck availability as early as possible (before "load") so UI can enable/disable hex mode quickly.
    try {
      const runtimeOk = supportsWebGL2Runtime();
      // We can't know if Mapbox picked WebGL2 until after it's initialized;
      // keep this as a "capability" signal for now.
      setDeckAvailable(runtimeOk ? null : false);
      setDeckError(runtimeOk ? null : "WebGL2 not available in this browser/environment.");
      deckEnabledRef.current = false;
    } catch {
      deckEnabledRef.current = false;
      setDeckAvailable(false);
      setDeckError("WebGL2 not available in this browser/environment.");
    }

    map.on("load", () => {
      ensureDemAndSky(map, terrainEnabled);

      // deck.gl overlay for hexagon aggregation (optional)
      // deck.gl requires WebGL2. If the user's environment only supports WebGL1, skip it gracefully
      // (Mapbox layers like scatter/heatmap will still work).
      const runtimeOk = supportsWebGL2Runtime();
      const mapOk = mapIsUsingWebGL2(map);
      const ok = runtimeOk && mapOk;
      deckEnabledRef.current = ok;
      setDeckAvailable(ok);
      setDeckError(ok ? null : runtimeOk ? "Mapbox is running on WebGL1 (deck.gl needs WebGL2)." : "WebGL2 not available.");
    });

    map.on("style.load", () => {
      // Re-attach terrain + sky + our data layers after a style switch.
      ensureDemAndSky(map, terrainEnabled);
      applyDatasetsToMap(map, datasetsRef.current);
    });

    // Click selection (on any known dataset point layer).
    map.on("click", (e: MapMouseEvent) => {
      const pointLayerIds = datasetsRef.current
        .map((d) => `${LAYER_ID_PREFIX}${d.id}:points`)
        .filter((id) => map.getLayer(id));
      if (!pointLayerIds.length) return;
      const features = map.queryRenderedFeatures(e.point, { layers: pointLayerIds }) as MapboxAny[];
      const f = features?.[0];
      if (!f) return;
      const props = f.properties || {};
      const fid = props.id ?? f.id ?? null;
      if (fid != null) setSelectedFeatureId(fid);
    });

    // Hover tooltip (lightweight HTML popup to avoid React re-render churn).
    map.on("mousemove", (e: MapMouseEvent) => {
      const pointLayerIds = datasetsRef.current
        .map((d) => `${LAYER_ID_PREFIX}${d.id}:points`)
        .filter((id) => map.getLayer(id));
      if (!pointLayerIds.length) return;
      const features = map.queryRenderedFeatures(e.point, { layers: pointLayerIds }) as MapboxAny[];
      const f = features?.[0];
      if (!f) {
        if (popupRef.current) popupRef.current.remove();
        popupRef.current = null;
        map.getCanvas().style.cursor = "";
        return;
      }
      map.getCanvas().style.cursor = "pointer";
      const props = f.properties || {};
      const html = `<div style="font-size:12px;line-height:1.25">
        <div style="font-weight:650;margin-bottom:4px">${props.english_name ?? props.mods_id ?? "Feature"}</div>
        <div style="color:#94a3b8">${props.major_commodity ?? ""}</div>
        <div style="color:#94a3b8">${props.admin_region ?? ""}</div>
      </div>`;
      if (!popupRef.current) {
        popupRef.current = new mapboxgl.Popup({ closeButton: false, closeOnClick: false, offset: 12 });
      }
      popupRef.current.setLngLat(e.lngLat).setHTML(html).addTo(map);
    });

    mapRef.current = map;
    return () => {
      popupRef.current?.remove();
      popupRef.current = null;
      if (deckRef.current) {
        try {
          map.removeControl(deckRef.current as unknown as mapboxgl.IControl);
        } catch {
          // ignore
        }
        deckRef.current = null;
      }
      map.remove();
      mapRef.current = null;
    };
  }, [config, styleUrl, terrainEnabled]); // intentionally NOT depending on datasets to keep map stable

  // Switch surface style without remounting map (keeps camera/state).
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    try {
      if (map.isStyleLoaded()) map.setStyle(styleUrl);
    } catch {
      // ignore
    }
  }, [styleUrl]);

  // Toggle terrain live.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (!map.isStyleLoaded()) return;
    try {
      if (terrainEnabled) map.setTerrain({ source: "mapbox-dem", exaggeration: 1.2 } as MapboxAny);
      else map.setTerrain(null as MapboxAny);
    } catch {
      // ignore; terrain might not be available until style load
    }
  }, [terrainEnabled]);

  // Sync datasets -> sources/layers (without remounting the map).
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const onStyleReady = () => {
      applyDatasetsToMap(map, datasets);

      // Auto-fit to fresh agent results so users immediately see "all points" in view.
      const agent = datasets.find((d) => d.id === "agent-occurrences");
      if (agent?.visible) {
        const n = (agent.data as any)?.features?.length ?? 0;
        const fitKey = `${agent.id}:${n}`;
        if (n > 0 && fitKey !== lastFitKeyRef.current) {
          const b = computePointBbox(agent.data);
          if (b) {
            lastFitKeyRef.current = fitKey;
            try {
              map.fitBounds(b as any, { padding: 40, duration: 800, maxZoom: 7 });
            } catch {
              // ignore
            }
          }
        }
      }
    };

    if (map.isStyleLoaded()) onStyleReady();
    else map.once("idle", onStyleReady);
  }, [datasets]);

  // Hexagon aggregation via deck.gl overlay (updates without touching Mapbox sources/layers).
  useEffect(() => {
    const map = mapRef.current;
    const overlay = deckRef.current;
    if (!map) return;

    const hexDatasets = datasets
      .filter((d) => d.kind !== "raster")
      .filter((d) => d.visible && (d.style.pointMode ?? "scatter") === "hexagon")
      .filter((d) => {
        const feats: any[] = (d.data as any)?.features ?? [];
        return feats.length > 0;
      });

    if (!hexDatasets.length) {
      if (overlay) overlay.setProps({ layers: [] });
      return;
    }

    if (!deckEnabledRef.current) {
      // WebGL2 isn't available; don't attempt to start deck.gl.
      return;
    }

    // Lazily initialize deck.gl only when needed (prevents WebGL2 errors on unsupported systems).
    (async () => {
      if (!deckRef.current) {
        try {
          const { MapboxOverlay } = await import("@deck.gl/mapbox");
          const o = new MapboxOverlay({ interleaved: true, layers: [] });
          deckRef.current = o;
          map.addControl(o as unknown as mapboxgl.IControl);
        } catch {
          deckEnabledRef.current = false;
          setDeckAvailable(false);
          setDeckError("Failed to initialize deck.gl (dynamic import failed).");
          return;
        }
      }

      const { HexagonLayer } = await import("@deck.gl/aggregation-layers");

      const layers = hexDatasets
      .map((d) => {
        const feats: any[] = (d.data as any)?.features ?? [];
        const pts: any[] = [];
        for (const f of feats) {
          const g = f?.geometry;
          if (!g || !g.type) continue;
          if (g.type === "Point" && Array.isArray(g.coordinates)) {
            pts.push(g.coordinates);
          } else if (g.type === "MultiPoint" && Array.isArray(g.coordinates)) {
            for (const c of g.coordinates) {
              if (Array.isArray(c)) pts.push(c);
            }
          }
        }

        // deck.gl draws 3D hex bins from input points (lon/lat).
        return new HexagonLayer({
          id: `hex:${d.id}`,
          data: pts,
          getPosition: (p: any) => p,
          radius: d.style.hexRadius ?? 7000,
          coverage: 0.85,
          elevationScale: d.style.hexElevationScale ?? 25,
          extruded: true,
          pickable: true,
          opacity: Math.min(0.9, d.style.opacity),
          colorRange: [
            [59, 130, 246],
            [34, 197, 94],
            [245, 158, 11],
            [239, 68, 68],
          ],
        });
      });

      deckRef.current?.setProps({ layers });
      setDeckError(null);
    })();
  }, [datasets]);

  // Sync selection filter.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (!map.isStyleLoaded()) return;
    datasets.forEach((d) => {
      const selLayerId = `${LAYER_ID_PREFIX}${d.id}:selected`;
      if (!map.getLayer(selLayerId)) return;
      const fid = selectedFeatureId ?? -999999;
      map.setFilter(selLayerId, ["all", ["==", ["geometry-type"], "Point"], ["==", ["get", "id"], fid]] as MapboxAny);
    });
  }, [selectedFeatureId, datasets]);

  // Container fills its panel; Mapbox reads size from this element.
  return <div ref={containerRef} style={{ width: "100%", height: "100%" }} />;
}

