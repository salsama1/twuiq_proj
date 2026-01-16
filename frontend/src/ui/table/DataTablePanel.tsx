import { useEffect, useMemo, useState } from "react";
import { getCoreRowModel, getFilteredRowModel, getSortedRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { useAppStore } from "../../store/appStore";
import type { OccurrenceInfo } from "../../types/api";

/**
 * DataTablePanel
 *
 * Responsibilities:
 * - Render a tabular view of `OccurrenceInfo[]` (usually produced by the agent).
 * - Provide table → map selection sync (click row selects the corresponding map feature).
 * - Show map → table selection sync (selectedFeatureId highlights the row).
 */
export function DataTablePanel() {
  const rows = useAppStore((s) => s.occurrences);
  const lastArtifacts = useAppStore((s) => s.lastArtifacts);
  const selectedFeatureId = useAppStore((s) => s.map.selectedFeatureId);
  const setSelectedFeatureId = useAppStore((s) => s.map.setSelectedFeatureId);

  const hasRows = rows.length > 0;
  const hasStatsByRegion = !!(lastArtifacts?.stats_by_region?.length);
  const hasStatsByType = !!(lastArtifacts?.stats_by_type?.length);
  const hasStatsRegionByType = !!(lastArtifacts?.stats_region_by_type?.length);

  const chartOptions = useMemo(() => {
    // Disable row-based modes when there are no table rows.
    const rowEnabled = hasRows;
    return [
      { id: "commodity", label: "By Commodity", enabled: rowEnabled },
      { id: "region", label: "By Region", enabled: rowEnabled },
      { id: "type", label: "By Type", enabled: rowEnabled },
      { id: "status", label: "By Status", enabled: rowEnabled },
      { id: "stats_by_region", label: "Top Regions (stats)", enabled: hasStatsByRegion },
      { id: "stats_by_type", label: "Top Types (stats)", enabled: hasStatsByType },
      { id: "stats_region_by_type", label: "Region × Type (stats)", enabled: hasStatsRegionByType },
    ] as const;
  }, [hasRows, hasStatsByRegion, hasStatsByType, hasStatsRegionByType]);

  const [chartMode, setChartMode] = useState<string>("commodity");

  // Auto-switch to a mode that has data (prevents the "empty chart" confusion for stats queries).
  useEffect(() => {
    const cur = chartOptions.find((o) => o.id === chartMode);
    if (cur?.enabled) return;

    if (hasStatsRegionByType) setChartMode("stats_region_by_type");
    else if (hasStatsByType) setChartMode("stats_by_type");
    else if (hasStatsByRegion) setChartMode("stats_by_region");
    else setChartMode("commodity");
  }, [chartMode, chartOptions, hasStatsByRegion, hasStatsByType, hasStatsRegionByType]);

  function downloadBlob(filename: string, blob: Blob) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function csvEscape(v: unknown): string {
    const s = v == null ? "" : String(v);
    // Quote if it contains special chars; escape quotes by doubling.
    if (/[",\r\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
    return s;
  }

  function exportCsv() {
    const header = [
      "mods_id",
      "english_name",
      "arabic_name",
      "major_commodity",
      "admin_region",
      "occurrence_type",
      "exploration_status",
      "occurrence_importance",
      "latitude",
      "longitude",
      "elevation",
      "description",
    ];
    const lines: string[] = [];
    lines.push(header.join(","));
    for (const r of rows) {
      lines.push(
        [
          r.mods_id,
          r.english_name,
          r.arabic_name ?? "",
          r.major_commodity,
          r.admin_region ?? "",
          r.occurrence_type ?? "",
          r.exploration_status ?? "",
          r.occurrence_importance ?? "",
          r.latitude,
          r.longitude,
          r.elevation ?? "",
          r.description ?? "",
        ]
          .map(csvEscape)
          .join(",")
      );
    }
    // Add UTF-8 BOM so Excel renders Arabic correctly.
    const csv = "\ufeff" + lines.join("\r\n");
    downloadBlob(`results_${rows.length}.csv`, new Blob([csv], { type: "text/csv;charset=utf-8" }));
  }

  function exportGeoJson() {
    const fc = {
      type: "FeatureCollection",
      features: rows.map((r) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [r.longitude, r.latitude] },
        properties: { ...r },
      })),
    };
    downloadBlob(
      `results_${rows.length}.geojson`,
      new Blob([JSON.stringify(fc, null, 2)], { type: "application/geo+json;charset=utf-8" })
    );
  }

  const chartData = useMemo(() => {
    // If user selected stats_by_region, render from artifacts even if table is empty.
    if (chartMode === "stats_by_region") {
      const items =
        (lastArtifacts?.stats_by_region ?? [])
          .filter((r) => !!r)
          .map((r: any) => ({ label: r.admin_region ?? "Unknown", count: Number(r.count ?? 0) }))
          .sort((a, b) => b.count - a.count)
          .slice(0, 12);
      const max = items.reduce((m, it) => Math.max(m, it.count), 1);
      return { modeLabel: "Top Regions (stats)", items, max, hasAny: items.length > 0 };
    }

    if (chartMode === "stats_by_type") {
      const items =
        (lastArtifacts?.stats_by_type ?? [])
          .filter((r) => !!r)
          .map((r: any) => ({ label: r.occurrence_type ?? "Unknown", count: Number(r.count ?? 0) }))
          .sort((a, b) => b.count - a.count)
          .slice(0, 12);
      const max = items.reduce((m, it) => Math.max(m, it.count), 1);
      return { modeLabel: "Top Types (stats)", items, max, hasAny: items.length > 0 };
    }

    if (chartMode === "stats_region_by_type") {
      const items =
        (lastArtifacts?.stats_region_by_type ?? [])
          .filter((r) => !!r)
          .map((r: any) => ({
            label: `${r.admin_region ?? "Unknown"} — ${r.occurrence_type ?? "Unknown"}`,
            count: Number(r.count ?? 0),
          }))
          .sort((a, b) => b.count - a.count)
          .slice(0, 12);
      const max = items.reduce((m, it) => Math.max(m, it.count), 1);
      return { modeLabel: "Region × Type (stats)", items, max, hasAny: items.length > 0 };
    }

    // Otherwise render from table rows.
    const getKey = (r: OccurrenceInfo) => {
      if (chartMode === "region") return (r.admin_region || "Unknown").trim() || "Unknown";
      if (chartMode === "type") return (r.occurrence_type || "Unknown").trim() || "Unknown";
      if (chartMode === "status") return (r.exploration_status || "Unknown").trim() || "Unknown";
      return (r.major_commodity || "Unknown").trim() || "Unknown";
    };
    const counts = new Map<string, number>();
    for (const r of rows) counts.set(getKey(r), (counts.get(getKey(r)) ?? 0) + 1);
    const items = Array.from(counts.entries())
      .map(([label, count]) => ({ label, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 12);
    const max = items.reduce((m, it) => Math.max(m, it.count), 1);
    const modeLabel = chartOptions.find((o) => o.id === chartMode)?.label ?? "Chart";
    return { modeLabel, items, max, hasAny: items.length > 0 };
  }, [rows, chartMode, chartOptions, lastArtifacts?.stats_by_region, lastArtifacts?.stats_by_type, lastArtifacts?.stats_region_by_type]);

  // Keep columns stable across renders for table performance.
  const columns = useMemo<ColumnDef<OccurrenceInfo>[]>(
    () => [
      { header: "MODS", accessorKey: "mods_id" },
      { header: "Name", accessorKey: "english_name" },
      { header: "Commodity", accessorKey: "major_commodity" },
      { header: "Region", accessorKey: "admin_region" },
      { header: "Type", accessorKey: "occurrence_type" },
      { header: "Status", accessorKey: "exploration_status" },
    ],
    []
  );

  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    state: {},
  });

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div className="panelHeader">
        <div>
          <div className="panelTitle">Data Table</div>
          <div className="muted" style={{ fontSize: 12 }}>
            Map ↔ table selection sync (click a row or a point)
          </div>
        </div>
        <div className="krow" style={{ gap: 8 }}>
          <button className="btn" onClick={exportCsv} disabled={rows.length === 0}>
            Export CSV
          </button>
          <button className="btn" onClick={exportGeoJson} disabled={rows.length === 0}>
            Export GeoJSON
          </button>
          <div className="muted" style={{ fontSize: 12 }}>
            Rows: <b style={{ color: "var(--text)" }}>{rows.length}</b>
          </div>
        </div>
      </div>

      {/* Lightweight chart summary of current results */}
      <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--border)" }}>
        <div className="krow" style={{ justifyContent: "space-between", gap: 10, marginBottom: 8 }}>
          <div style={{ fontWeight: 650 }}>Chart</div>
          <div className="krow" style={{ gap: 8 }}>
            <span className="muted" style={{ fontSize: 12 }}>
              {chartData.modeLabel}
            </span>
            <select
              className="input"
              style={{ height: 34, padding: "6px 10px" }}
              value={chartMode}
              onChange={(e) => setChartMode(e.target.value)}
            >
              {chartOptions.map((o) => (
                <option key={o.id} value={o.id} disabled={!o.enabled}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {(!chartData.hasAny) ? (
          <div className="muted" style={{ fontSize: 12 }}>
            Ask the agent for results (or a stats query), then the chart will appear here.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {chartData.items.map((it) => {
              const w = Math.max(2, Math.round((it.count / chartData.max) * 100));
              return (
                <div key={it.label} style={{ display: "grid", gridTemplateColumns: "140px 1fr 40px", gap: 10, alignItems: "center" }}>
                  <div
                    title={it.label}
                    style={{
                      fontSize: 12,
                      color: "var(--text)",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {it.label}
                  </div>
                  <div style={{ height: 10, background: "rgba(255,255,255,0.05)", borderRadius: 999, overflow: "hidden" }}>
                    <div
                      style={{
                        width: `${w}%`,
                        height: "100%",
                        background: "linear-gradient(90deg, rgba(59,130,246,0.85), rgba(34,197,94,0.85))",
                      }}
                    />
                  </div>
                  <div className="muted" style={{ fontSize: 12, textAlign: "right" }}>
                    {it.count}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div style={{ overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => (
                  <th
                    key={h.id}
                    style={{
                      textAlign: "left",
                      padding: "10px 12px",
                      borderBottom: "1px solid var(--border)",
                      position: "sticky",
                      top: 0,
                      background: "var(--panel)",
                      cursor: h.column.getCanSort() ? "pointer" : "default",
                    }}
                    onClick={h.column.getToggleSortingHandler()}
                  >
                    {String(h.column.columnDef.header)}
                    {h.column.getIsSorted() === "asc" ? " ▲" : h.column.getIsSorted() === "desc" ? " ▼" : ""}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((r) => {
              const o = r.original;
              // Selected row is driven by the shared `selectedFeatureId`.
              const isSel = selectedFeatureId != null && String(selectedFeatureId) === String(o.mods_id);
              return (
                <tr
                  key={r.id}
                  style={{
                    background: isSel ? "rgba(34,197,94,0.10)" : "transparent",
                    borderBottom: "1px solid rgba(35,48,71,0.5)",
                    cursor: "pointer",
                  }}
                  // Clicking a row selects the corresponding map feature.
                  onClick={() => setSelectedFeatureId(o.mods_id)}
                >
                  {r.getVisibleCells().map((c) => (
                    <td key={c.id} style={{ padding: "10px 12px", color: "var(--text)" }}>
                      {String(c.getValue() ?? "")}
                    </td>
                  ))}
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={columns.length} style={{ padding: 14 }} className="muted">
                  No data loaded yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

