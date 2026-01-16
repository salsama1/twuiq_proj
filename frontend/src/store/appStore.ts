import { create } from "zustand";
import type { AppConfig } from "../config/types";
import type { GeoJSONFeatureCollection } from "../types/geojson";
import type { AgentArtifacts, OccurrenceInfo, ToolTraceItem, WorkflowStep } from "../types/api";

/**
 * Global application state (Zustand).
 *
 * Design goals:
 * - Keep map instance stable (MapView reads state and updates layers without remounting).
 * - Keep UI panels decoupled: chat produces data, map + table consume it via the store.
 * - Store is small and serializable (except refs which live in components).
 */
export type DatasetLayer = {
  id: string;
  name: string;
  kind: "points" | "polygon" | "mixed" | "raster";
  data: GeoJSONFeatureCollection;
  raster?: {
    tileUrlTemplate: string; // .../tiles/{z}/{x}/{y}.png
    tileSize?: number;
  };
  visible: boolean;
  style: {
    // Point rendering mode
    pointMode?: "scatter" | "heatmap" | "hexagon";
    color: string;
    opacity: number; // 0..1
    radius: number; // px (points)
    // Heatmap params (Mapbox heatmap layer)
    heatmapRadius?: number; // px
    heatmapIntensity?: number; // 0..?
    // Hexagon params (deck.gl aggregation)
    hexRadius?: number; // meters
    hexElevationScale?: number;
    extrude: boolean; // polygons
    extrudeHeight: number; // meters-ish, Mapbox uses arbitrary units
  };
};

/**
 * Chat messages are stored as a simple list for rendering.
 * (We intentionally keep tool traces optional; the UI can choose to hide them.)
 */
export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
  createdAt: number;
  plan?: WorkflowStep[];
  toolTrace?: ToolTraceItem[];
};

type AppState = {
  // Runtime config
  config: AppConfig | null;
  configHint: string | null;
  setConfig: (config: AppConfig | null, hint: string | null) => void;

  // UI layout
  chatCollapsed: boolean;
  setChatCollapsed: (v: boolean) => void;

  // Map state
  map: {
    terrainEnabled: boolean;
    setTerrainEnabled: (v: boolean) => void;
    terrainSurface: "original" | "street" | "satellite";
    setTerrainSurface: (v: "original" | "street" | "satellite") => void;
    deckAvailable: boolean | null;
    setDeckAvailable: (v: boolean | null) => void;
    deckError: string | null;
    setDeckError: (v: string | null) => void;
    hoveredFeatureId: number | string | null;
    setHoveredFeatureId: (id: number | string | null) => void;
    selectedFeatureId: number | string | null;
    setSelectedFeatureId: (id: number | string | null) => void;
  };

  // Data/layers
  datasets: DatasetLayer[];
  activeDatasetId: string | null;
  upsertDataset: (layer: DatasetLayer) => void;
  setActiveDatasetId: (id: string | null) => void;
  setDatasetVisible: (id: string, visible: boolean) => void;
  updateDatasetStyle: (id: string, patch: Partial<DatasetLayer["style"]>) => void;

  // Table backing data (normalized)
  occurrences: OccurrenceInfo[];
  setOccurrences: (rows: OccurrenceInfo[]) => void;

  // Last agent artifacts (stats, exports, etc) for panels like charts.
  lastArtifacts: AgentArtifacts | null;
  setLastArtifacts: (a: AgentArtifacts | null) => void;

  // Chat
  sessionId: string | null;
  setSessionId: (sid: string | null) => void;
  chat: {
    messages: ChatMessage[];
    isBusy: boolean;
    pushMessage: (m: ChatMessage) => void;
    setBusy: (v: boolean) => void;
    clear: () => void;
  };
};

export const useAppStore = create<AppState>((set) => ({
  config: null,
  configHint: null,
  setConfig: (config, hint) => set({ config, configHint: hint }),

  // UI layout state (used by ChatPanel + App layout to avoid unmounting map).
  chatCollapsed: false,
  setChatCollapsed: (v) => set({ chatCollapsed: v }),

  // Map-related UI state (selection + style surface + 3D terrain enablement).
  map: {
    terrainEnabled: true,
    setTerrainEnabled: (v) => set((s) => ({ map: { ...s.map, terrainEnabled: v } })),
    terrainSurface: "original",
    setTerrainSurface: (v) => set((s) => ({ map: { ...s.map, terrainSurface: v } })),
    deckAvailable: null,
    setDeckAvailable: (v) => set((s) => ({ map: { ...s.map, deckAvailable: v } })),
    deckError: null,
    setDeckError: (v) => set((s) => ({ map: { ...s.map, deckError: v } })),
    hoveredFeatureId: null,
    setHoveredFeatureId: (id) => set((s) => ({ map: { ...s.map, hoveredFeatureId: id } })),
    selectedFeatureId: null,
    setSelectedFeatureId: (id) => set((s) => ({ map: { ...s.map, selectedFeatureId: id } })),
  },

  // Datasets drive map layers; most are created from agent artifacts.
  datasets: [],
  activeDatasetId: null,
  upsertDataset: (layer) =>
    set((s) => {
      const idx = s.datasets.findIndex((d) => d.id === layer.id);
      const datasets = [...s.datasets];
      if (idx >= 0) datasets[idx] = layer;
      else datasets.unshift(layer);
      const activeDatasetId = s.activeDatasetId ?? layer.id;
      return { datasets, activeDatasetId };
    }),
  setActiveDatasetId: (id) => set({ activeDatasetId: id }),
  setDatasetVisible: (id, visible) =>
    set((s) => ({
      datasets: s.datasets.map((d) => (d.id === id ? { ...d, visible } : d)),
    })),
  updateDatasetStyle: (id, patch) =>
    set((s) => ({
      datasets: s.datasets.map((d) => (d.id === id ? { ...d, style: { ...d.style, ...patch } } : d)),
    })),

  // Table rows (kept separate so table can render independently from dataset GeoJSON).
  occurrences: [],
  setOccurrences: (rows) => set({ occurrences: rows }),

  lastArtifacts: null,
  setLastArtifacts: (a) => set({ lastArtifacts: a }),

  // Chat state; sessionId allows server-side continuity across prompts.
  sessionId: null,
  setSessionId: (sid) => set({ sessionId: sid }),

  chat: {
    messages: [],
    isBusy: false,
    pushMessage: (m) => set((s) => ({ chat: { ...s.chat, messages: [...s.chat.messages, m] } })),
    setBusy: (v) => set((s) => ({ chat: { ...s.chat, isBusy: v } })),
    clear: () => set((s) => ({ chat: { ...s.chat, messages: [] } })),
  },
}));

