import { useEffect, useRef } from "react";
import { Panel, PanelGroup, PanelResizeHandle, type ImperativePanelHandle } from "react-resizable-panels";
import { loadAppConfig } from "../config/loadConfig";
import { useAppStore } from "../store/appStore";
import { LayersPanel } from "./panels/LayersPanel";
import { ChatPanel } from "./panels/ChatPanel";
import { DataTablePanel } from "./table/DataTablePanel";
import { MapView } from "./map/MapView";

/**
 * App shell + layout.
 *
 * Responsibilities:
 * - Load runtime config from `public/config.json` (or example fallback).
 * - Render the Kepler-like resizable layout: layers (left), map+table (center), chat (right).
 * - Keep map state stable while panels resize/collapse.
 */
export function App() {
  const config = useAppStore((s) => s.config);
  const configHint = useAppStore((s) => s.configHint);
  const setConfig = useAppStore((s) => s.setConfig);
  const setChatCollapsed = useAppStore((s) => s.setChatCollapsed);
  const chatPanelRef = useRef<ImperativePanelHandle>(null);

  // Load runtime config once on startup.
  useEffect(() => {
    void (async () => {
      const { config, hint } = await loadAppConfig();
      setConfig(config, hint);
    })();
  }, [setConfig]);

  // We intentionally do not ship a token; show banners if config/token are missing.
  const missingToken = !config?.mapbox?.token || config.mapbox.token.includes("PASTE_");

  return (
    <div className="app-shell">
      {configHint && (
        <div className="banner">
          <div className="bannerTitle">Frontend config needed</div>
          <div className="bannerText">
            {configHint} <br />
            This UI expects a <b>public</b> Mapbox token (usually starts with <code>pk.</code>), not a secret token.
          </div>
        </div>
      )}
      {missingToken && (
        <div className="banner" style={{ top: configHint ? 92 : 12 }}>
          <div className="bannerTitle">Mapbox token missing</div>
          <div className="bannerText">
            Create <code>frontend/public/config.json</code> (copy from <code>config.example.json</code>) and set{" "}
            <code>mapbox.token</code>.
          </div>
        </div>
      )}

      {/* Resizable tri-panel layout (left: layers, center: map+table, right: collapsible chat). */}
      <PanelGroup direction="horizontal" style={{ height: "100%" }}>
        <Panel defaultSize={20} minSize={15} className="panel">
          <LayersPanel />
        </Panel>
        <PanelResizeHandle style={{ width: 6, background: "#0b0f14", cursor: "col-resize" }} />
        <Panel defaultSize={60} minSize={30} style={{ position: "relative" }}>
          <PanelGroup direction="vertical" style={{ height: "100%" }}>
            <Panel defaultSize={70} minSize={30}>
              <MapView />
            </Panel>
            <PanelResizeHandle style={{ height: 6, background: "#0b0f14", cursor: "row-resize" }} />
            <Panel defaultSize={30} minSize={15} className="panel" style={{ borderTop: "1px solid var(--border)" }}>
              <DataTablePanel />
            </Panel>
          </PanelGroup>
        </Panel>
        <PanelResizeHandle style={{ width: 6, background: "#0b0f14", cursor: "col-resize" }} />
        <Panel
          ref={chatPanelRef}
          defaultSize={20}
          minSize={12}
          collapsible
          collapsedSize={4}
          onCollapse={() => setChatCollapsed(true)}
          onExpand={() => setChatCollapsed(false)}
          className="panel"
          style={{ borderLeft: "1px solid var(--border)" }}
        >
          {/* Chat panel is collapsible; map/table should remain functional without state reset. */}
          <ChatPanel onCollapse={() => chatPanelRef.current?.collapse()} onExpand={() => chatPanelRef.current?.expand()} />
        </Panel>
      </PanelGroup>
    </div>
  );
}

