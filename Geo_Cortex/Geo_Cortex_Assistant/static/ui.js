const outputEl = document.getElementById("output");
const statusEl = document.getElementById("status");
const queryEl = document.getElementById("query");
const responseTextEl = document.getElementById("responseText");
const toggleRawBtn = document.getElementById("toggleRaw");

const commodityEl = document.getElementById("commodity");
const regionEl = document.getElementById("region");
const occTypeEl = document.getElementById("occType");
const limitEl = document.getElementById("limit");
const latEl = document.getElementById("lat");
const lonEl = document.getElementById("lon");
const radiusEl = document.getElementById("radius");
const binKmEl = document.getElementById("binKm");

const dlGeojsonEl = document.getElementById("dlGeojson");
const dlCsvEl = document.getElementById("dlCsv");
let dlLock = false;

const togglePointsEl = document.getElementById("togglePoints");
const toggleHeatEl = document.getElementById("toggleHeat");

const tableWrapEl = document.getElementById("tableWrap");
const tableEl = document.getElementById("resultsTable");
const theadEl = tableEl.querySelector("thead");
const tbodyEl = tableEl.querySelector("tbody");

const runAgentBtn = document.getElementById("runAgent");
const runRagBtn = document.getElementById("runRag");
const statsByRegionBtn = document.getElementById("statsByRegion");
const importanceBtn = document.getElementById("importance");
const heatmapBtn = document.getElementById("heatmap");

function numOrNull(v) {
  if (v === null || v === undefined) return null;
  if (typeof v === "string" && v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function buildQueryParams(extra = {}) {
  const p = new URLSearchParams();
  const commodity = commodityEl.value.trim();
  const region = regionEl.value.trim();
  const occType = occTypeEl.value.trim();
  const limit = numOrNull(limitEl.value);
  const lat = numOrNull(latEl.value);
  const lon = numOrNull(lonEl.value);
  const radius = numOrNull(radiusEl.value);

  if (commodity) p.set("commodity", commodity);
  if (region) p.set("region", region);
  if (occType) p.set("occurrence_type", occType);
  if (limit) p.set("limit", String(limit));
  if (lat !== null) p.set("lat", String(lat));
  if (lon !== null) p.set("lon", String(lon));
  if (radius !== null && radius > 0) p.set("radius_km", String(radius));

  for (const [k, v] of Object.entries(extra)) {
    if (v === null || v === undefined) continue;
    p.set(k, String(v));
  }
  return p;
}

function updateDownloadLinks() {
  const p = buildQueryParams();
  dlGeojsonEl.href = `/export/geojson?${p.toString()}`;
  dlCsvEl.href = `/export/csv?${p.toString()}`;
}

for (const el of [commodityEl, regionEl, occTypeEl, limitEl, latEl, lonEl, radiusEl]) {
  el.addEventListener("input", updateDownloadLinks);
}
updateDownloadLinks();

function withDownloadLock(fn) {
  return (e) => {
    e.preventDefault();
    if (dlLock) return;
    dlLock = true;
    try {
      fn();
    } finally {
      // prevent accidental double-click / multi-download
      setTimeout(() => { dlLock = false; }, 1200);
    }
  };
}

dlGeojsonEl.addEventListener("click", withDownloadLock(() => {
  window.location.assign(dlGeojsonEl.href);
}));

dlCsvEl.addEventListener("click", withDownloadLock(() => {
  window.location.assign(dlCsvEl.href);
}));

// Map
const map = L.map("map").setView([24.7136, 46.6753], 6);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

const pointsLayer = L.layerGroup().addTo(map);
const binsLayer = L.layerGroup().addTo(map);
const legendEl = document.getElementById("legend");
const legendMinEl = document.getElementById("legendMin");
const legendMaxEl = document.getElementById("legendMax");

let highlightMarker = null;

function clearMap() {
  pointsLayer.clearLayers();
  binsLayer.clearLayers();
  if (highlightMarker) {
    try { map.removeLayer(highlightMarker); } catch {}
    highlightMarker = null;
  }
  legendEl.classList.add("hidden");
}

togglePointsEl.addEventListener("change", () => {
  if (togglePointsEl.checked) {
    if (!map.hasLayer(pointsLayer)) pointsLayer.addTo(map);
  } else {
    if (map.hasLayer(pointsLayer)) map.removeLayer(pointsLayer);
  }
});

toggleHeatEl.addEventListener("change", () => {
  if (toggleHeatEl.checked) {
    if (!map.hasLayer(binsLayer)) binsLayer.addTo(map);
  } else {
    if (map.hasLayer(binsLayer)) map.removeLayer(binsLayer);
  }
});

function addOccurrences(occurrences) {
  if (!Array.isArray(occurrences)) return;
  for (const o of occurrences) {
    const lat = o.latitude;
    const lon = o.longitude;
    if (typeof lat !== "number" || typeof lon !== "number") continue;
    const title = `${o.mods_id} — ${o.english_name || ""}`.trim();
    L.marker([lat, lon]).addTo(pointsLayer).bindPopup(title);
  }
}

function zoomTo(lat, lon, popupText) {
  if (typeof lat !== "number" || typeof lon !== "number") return;
  map.setView([lat, lon], Math.max(map.getZoom(), 9));
  if (popupText) {
    if (highlightMarker) {
      try { map.removeLayer(highlightMarker); } catch {}
    }
    highlightMarker = L.circleMarker([lat, lon], {
      radius: 10,
      color: "#111827",
      fillColor: "#22c55e",
      fillOpacity: 0.9,
      weight: 2,
    }).addTo(map).bindPopup(popupText).openPopup();
  }
}

function addGeojson(fc) {
  if (!fc || fc.type !== "FeatureCollection") return;
  const layer = L.geoJSON(fc, {
    onEachFeature: (feature, layer) => {
      const p = feature.properties || {};
      const title = `${p.mods_id || ""} — ${p.english_name || ""}`.trim();
      layer.bindPopup(title);
    },
  });
  layer.addTo(pointsLayer);
  try {
    map.fitBounds(layer.getBounds(), { padding: [20, 20] });
  } catch {}
}

function heatColor(t) {
  // t in [0,1] -> yellow -> orange -> red
  const stops = [
    { t: 0.0, r: 255, g: 247, b: 188 }, // #fff7bc
    { t: 0.5, r: 254, g: 196, b: 79 },  // #fec44f
    { t: 1.0, r: 240, g: 59,  b: 32 },  // #f03b20
  ];
  const a = t <= 0.5 ? stops[0] : stops[1];
  const b = t <= 0.5 ? stops[1] : stops[2];
  const localT = t <= 0.5 ? (t / 0.5) : ((t - 0.5) / 0.5);
  const r = Math.round(a.r + (b.r - a.r) * localT);
  const g = Math.round(a.g + (b.g - a.g) * localT);
  const bl = Math.round(a.b + (b.b - a.b) * localT);
  return `rgb(${r}, ${g}, ${bl})`;
}

function addHeatmapBins(bins) {
  if (!Array.isArray(bins)) return;
  if (!bins.length) {
    legendEl.classList.add("hidden");
    return;
  }

  const counts = bins.map(b => Number(b.count)).filter(n => Number.isFinite(n));
  const maxCount = counts.length ? Math.max(...counts) : 0;
  const minCount = counts.length ? Math.min(...counts) : 0;
  legendMinEl.textContent = String(minCount);
  legendMaxEl.textContent = String(maxCount);
  legendEl.classList.remove("hidden");

  for (const b of bins) {
    const lat = b.lat, lon = b.lon, count = b.count;
    if (typeof lat !== "number" || typeof lon !== "number") continue;
    const c = (typeof count === "number" && Number.isFinite(count)) ? count : 0;
    const t = maxCount > 0 ? Math.min(1, c / maxCount) : 0;
    const color = heatColor(t);
    const radius = Math.min(40000, 4000 + c * 900);
    L.circle([lat, lon], {
      radius,
      color,
      fillColor: color,
      fillOpacity: 0.35,
      weight: 1,
    }).addTo(binsLayer).bindPopup(`Count: ${count}`);
  }
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw data;
  return data;
}

function showOutput(obj) {
  outputEl.textContent = JSON.stringify(obj, null, 2);
  const resp = obj?.response;
  responseTextEl.textContent = typeof resp === "string" ? resp : "";
}

// Raw JSON toggle
let rawVisible = false;
function setRawVisible(v) {
  rawVisible = v;
  outputEl.style.display = rawVisible ? "block" : "none";
  toggleRawBtn.textContent = rawVisible ? "Hide raw JSON" : "Show raw JSON";
}
setRawVisible(false);
toggleRawBtn.addEventListener("click", () => setRawVisible(!rawVisible));

function setStatus(state, text) {
  statusEl.classList.remove("idle", "loading", "error");
  statusEl.classList.add(state);
  statusEl.textContent = text;
}

function setBusy(isBusy) {
  for (const btn of [runAgentBtn, runRagBtn, statsByRegionBtn, importanceBtn, heatmapBtn]) {
    if (!btn) continue;
    btn.disabled = isBusy;
    btn.style.opacity = isBusy ? "0.6" : "1";
    btn.style.cursor = isBusy ? "not-allowed" : "pointer";
  }
}

function renderTable(rows, columns) {
  theadEl.innerHTML = "";
  tbodyEl.innerHTML = "";

  if (!Array.isArray(rows) || rows.length === 0) {
    tableWrapEl.querySelector(".tableHint").textContent = "No rows returned.";
    return;
  }

  tableWrapEl.querySelector(".tableHint").textContent = `${rows.length} rows`;

  const trh = document.createElement("tr");
  for (const c of columns) {
    const th = document.createElement("th");
    th.textContent = c;
    trh.appendChild(th);
  }
  theadEl.appendChild(trh);

  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.style.cursor = "pointer";
    tr.addEventListener("click", () => {
      const lat = r.latitude ?? r.lat;
      const lon = r.longitude ?? r.lon;
      const latN = typeof lat === "string" ? Number(lat) : lat;
      const lonN = typeof lon === "string" ? Number(lon) : lon;
      const title = r.english_name
        ? `${r.mods_id || ""} — ${r.english_name}`.trim()
        : (r.mods_id || "");
      if (Number.isFinite(latN) && Number.isFinite(lonN)) {
        zoomTo(latN, lonN, title || `(${latN}, ${lonN})`);
      }
    });
    for (const c of columns) {
      const td = document.createElement("td");
      td.textContent = r?.[c] ?? "";
      tr.appendChild(td);
    }
    tbodyEl.appendChild(tr);
  }
}

function showResultsFromResponse(data) {
  // Prefer occurrences list
  if (Array.isArray(data?.occurrences) && data.occurrences.length) {
    const rows = data.occurrences.map(o => ({
      mods_id: o.mods_id,
      english_name: o.english_name,
      major_commodity: o.major_commodity,
      admin_region: o.admin_region,
      occurrence_type: o.occurrence_type,
      exploration_status: o.exploration_status,
      occurrence_importance: o.occurrence_importance,
      latitude: o.latitude,
      longitude: o.longitude,
    }));
    renderTable(rows, ["mods_id","english_name","major_commodity","admin_region","occurrence_type","exploration_status","occurrence_importance","latitude","longitude"]);
    return;
  }

  // Agent artifacts: stats
  if (Array.isArray(data?.artifacts?.stats_by_region) && data.artifacts.stats_by_region.length) {
    renderTable(data.artifacts.stats_by_region, ["admin_region","count"]);
    return;
  }
  if (Array.isArray(data?.artifacts?.importance_breakdown) && data.artifacts.importance_breakdown.length) {
    renderTable(data.artifacts.importance_breakdown, ["occurrence_importance","count"]);
    return;
  }
  if (Array.isArray(data?.artifacts?.heatmap_bins) && data.artifacts.heatmap_bins.length) {
    // Add bin_km as a displayed column if present in tool_trace.
    let binKm = null;
    if (Array.isArray(data?.tool_trace)) {
      const ht = [...data.tool_trace].reverse().find(t => t.tool === "heatmap_bins");
      binKm = ht?.args?.bin_km ?? null;
    }
    // Also include WHAT the count represents (current filters).
    const commodity = (data?.tool_trace?.slice?.().reverse?.().find?.(t => t.tool === "heatmap_bins")?.args?.commodity)
      ?? commodityEl.value.trim()
      ?? "";
    const region = (data?.tool_trace?.slice?.().reverse?.().find?.(t => t.tool === "heatmap_bins")?.args?.region)
      ?? regionEl.value.trim()
      ?? "";
    const occurrenceType = (data?.tool_trace?.slice?.().reverse?.().find?.(t => t.tool === "heatmap_bins")?.args?.occurrence_type)
      ?? occTypeEl.value.trim()
      ?? "";

    const rows = data.artifacts.heatmap_bins.map(b => ({
      ...b,
      bin_km: binKm ?? numOrNull(binKmEl.value),
      commodity: commodity || null,
      region: region || null,
      occurrence_type: occurrenceType || null,
      counted_entity: "occurrences",
    }));
    renderTable(rows, ["lat","lon","count","bin_km","commodity","region","occurrence_type","counted_entity"]);
    return;
  }
  if (Array.isArray(data?.artifacts?.nearest_results) && data.artifacts.nearest_results.length) {
    const rows = data.artifacts.nearest_results.map(n => ({
      distance_m: n.distance_m,
      mods_id: n.occurrence?.mods_id,
      english_name: n.occurrence?.english_name,
      major_commodity: n.occurrence?.major_commodity,
      admin_region: n.occurrence?.admin_region,
      latitude: n.occurrence?.latitude,
      longitude: n.occurrence?.longitude,
    }));
    renderTable(rows, ["distance_m","mods_id","english_name","major_commodity","admin_region","latitude","longitude"]);
    return;
  }

  // If none matched
  renderTable([], []);
}

async function fetchOccurrencesForFilters(limitOverride = 500) {
  const p = buildQueryParams({ limit: limitOverride });
  const res = await fetch(`/occurrences/mods/search?${p.toString()}`);
  const data = await res.json();
  if (!res.ok) throw data;
  return data;
}

document.getElementById("runAgent").addEventListener("click", async () => {
  clearMap();
  const q = queryEl.value.trim();
  if (!q) return;
  try {
    setBusy(true);
    setStatus("loading", "Running agent...");
    const data = await postJson("/agent/", { query: q, max_steps: 5 });
    showOutput(data);
    if (data.artifacts?.geojson) addGeojson(data.artifacts.geojson);
    if (data.artifacts?.heatmap_bins) addHeatmapBins(data.artifacts.heatmap_bins);
    if (data.occurrences) addOccurrences(data.occurrences);
    // If agent produced a heatmap but no points, overlay points using current filters.
    if (togglePointsEl.checked && data.artifacts?.heatmap_bins && (!data.occurrences || !data.occurrences.length) && !data.artifacts?.geojson) {
      try {
        const occs = await fetchOccurrencesForFilters(500);
        addOccurrences(occs);
      } catch {}
    }
    showResultsFromResponse(data);
    setStatus("idle", "Done");
  } catch (e) {
    showOutput(e);
    setStatus("error", "Request failed (see output)");
  } finally {
    setBusy(false);
  }
});

document.getElementById("runRag").addEventListener("click", async () => {
  clearMap();
  const q = queryEl.value.trim();
  if (!q) return;
  try {
    setBusy(true);
    setStatus("loading", "Running RAG...");
    const data = await postJson("/query/rag", { query: q });
    showOutput(data);
    if (data.occurrences) addOccurrences(data.occurrences);
    showResultsFromResponse(data);
    setStatus("idle", "Done");
  } catch (e) {
    showOutput(e);
    setStatus("error", "Request failed (see output)");
  } finally {
    setBusy(false);
  }
});

document.getElementById("statsByRegion").addEventListener("click", async () => {
  clearMap();
  try {
    setBusy(true);
    setStatus("loading", "Loading stats by region...");
    const p = buildQueryParams({ limit: numOrNull(limitEl.value) || 50 });
    const res = await fetch(`/stats/by-region?${p.toString()}`);
    const data = await res.json();
    showOutput(data);
    showResultsFromResponse({ artifacts: { stats_by_region: data } });
    setStatus("idle", "Done");
  } catch (e) {
    showOutput(e);
    setStatus("error", "Request failed (see output)");
  } finally {
    setBusy(false);
  }
});

document.getElementById("importance").addEventListener("click", async () => {
  clearMap();
  try {
    setBusy(true);
    setStatus("loading", "Loading importance breakdown...");
    const p = buildQueryParams();
    const res = await fetch(`/stats/importance?${p.toString()}`);
    const data = await res.json();
    showOutput(data);
    showResultsFromResponse({ artifacts: { importance_breakdown: data } });
    setStatus("idle", "Done");
  } catch (e) {
    showOutput(e);
    setStatus("error", "Request failed (see output)");
  } finally {
    setBusy(false);
  }
});

document.getElementById("heatmap").addEventListener("click", async () => {
  clearMap();
  try {
    setBusy(true);
    setStatus("loading", "Building heatmap bins...");
    const binKm = numOrNull(binKmEl.value) || 25;
    const p = buildQueryParams({ bin_km: binKm, limit: 200 });
    const res = await fetch(`/stats/heatmap?${p.toString()}`);
    const data = await res.json();
    showOutput(data);
    addHeatmapBins(data);
    // Overlay points so user can see both heatmap + pins.
    if (togglePointsEl.checked) {
      try {
        const occs = await fetchOccurrencesForFilters(500);
        addOccurrences(occs);
      } catch {}
    }
    // Provide context so the table can show what was counted.
    showResultsFromResponse({
      artifacts: { heatmap_bins: data },
      tool_trace: [{ tool: "heatmap_bins", args: { commodity: commodityEl.value.trim(), region: regionEl.value.trim(), occurrence_type: occTypeEl.value.trim(), bin_km: binKm } }],
    });
    setStatus("idle", "Done");
  } catch (e) {
    showOutput(e);
    setStatus("error", "Request failed (see output)");
  } finally {
    setBusy(false);
  }
});

