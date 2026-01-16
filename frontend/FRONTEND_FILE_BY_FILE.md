# Geo Cortex Assistant — Frontend (File-by-File Documentation)

This document explains the **current frontend implementation** in `frontend/` **file by file**: what each file does, how data flows between the agent → map → table, and where to extend features (layers, styling, streaming, etc).

---

## Quick start (Windows / PowerShell)

1) Create runtime config (NOT committed):

```powershell
Copy-Item .\public\config.example.json .\public\config.json
notepad .\public\config.json
```

Set:
- `backendUrl`: your FastAPI base URL (example: `http://127.0.0.1:8000`). Leave empty (`""`) when serving the frontend from the same FastAPI server.
- `mapbox.token`: **public** Mapbox token (starts with `pk.`)
- `mapbox.style`: optional “original” basemap style URL (used when Surface = Original)

2) Install + run:

```powershell
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

---

## Architecture (high level)

### UI layout
- **Left panel**: `LayersPanel` (dataset list + styling controls + “Map Settings → Surface”)
- **Center**: Map (Mapbox GL) + Table (react-table), resizable vertically
- **Right panel**: `ChatPanel` (agent chat), collapsible without resetting map state

### Data flow (agent → UI)

```text
ChatPanel (user prompt)
  -> POST {backendUrl}/agent
     -> AgentResponse { response, occurrences?, artifacts? }
        -> applyAgentArtifacts()
           -> store.setOccurrences()  (table data)
           -> store.upsertDataset()   (map layers: points/polygons/mixed)
              -> MapView reacts to store.datasets and renders:
                 - Scatter (Mapbox circle)
                 - Heatmap (Mapbox heatmap)
                 - Hexagon (deck.gl HexagonLayer over Mapbox)
        -> ChatPanel renders assistant text
```

### Map ↔ table selection sync
- Clicking a map point sets `map.selectedFeatureId`
- Clicking a table row sets `map.selectedFeatureId`
- `MapView` updates the “selected” highlight layer filter from `selectedFeatureId`

---

## Runtime config (public)

### `public/config.example.json`
Template config that is safe to commit. Used as a fallback so the UI can show a helpful banner if `config.json` is missing.

### `public/config.json` (local only, gitignored)
Your real runtime config. Contains Mapbox token and backend URL.

### `.gitignore`
Ignores `public/config.json` to avoid committing tokens.

---

## Project-level files

### `package.json`
Frontend dependencies + scripts.
- **Map & 3D**: `mapbox-gl`
- **Hexagon aggregation**: `@deck.gl/mapbox` + `@deck.gl/aggregation-layers`
- **Layout**: `react-resizable-panels`
- **Global state**: `zustand`
- **Table**: `@tanstack/react-table`

Scripts:
- `npm run dev`: dev server
- `npm run build`: typecheck + production build

### `vite.config.ts`
Vite config (React plugin). No proxy is configured; API calls use `backendUrl` from `config.json`.

### `index.html`
Root HTML (mounts React at `#root`).

---

## Source entrypoints

### `src/main.tsx`
React entrypoint.
- Imports Mapbox CSS: `mapbox-gl/dist/mapbox-gl.css`
- Imports app styles: `src/styles/index.css`
- Renders `src/ui/App.tsx`

### `src/App.tsx`
Compatibility re-export (keeps Vite template import paths working). The real app is `src/ui/App.tsx`.

---

## Config loading

### `src/config/types.ts`
Type definitions for `AppConfig`:
- `backendUrl`
- `mapbox.token`
- `mapbox.style` (optional)

### `src/config/loadConfig.ts`
Loads runtime config at startup:
- tries `/config.json`
- if missing, falls back to `/config.example.json` and returns a **hint string** shown in the UI banner

---

## State management

### `src/store/appStore.ts` (Zustand)
Single global store for:
- **Runtime config**: `config`, `setConfig`, `configHint`
- **Layout state**: `chatCollapsed`
- **Map state**:
  - `terrainEnabled` (kept enabled by UI; Mapbox terrain is applied in `MapView`)
  - `terrainSurface`: `"original" | "satellite" | "street"`
  - `selectedFeatureId`, `hoveredFeatureId`
- **Datasets / layers**:
  - `datasets[]` contains GeoJSON + style controls
  - `upsertDataset`, `setDatasetVisible`, `updateDatasetStyle`
- **Table data**: `occurrences[]`
- **Chat**: messages + busy state + session id

**Dataset styling fields** (used by map rendering):
- `pointMode`: `"scatter" | "heatmap" | "hexagon"`
- `color`, `opacity`, `radius`
- `heatmapRadius`, `heatmapIntensity`
- `hexRadius`, `hexElevationScale`
- `extrude`, `extrudeHeight` (for polygons)

---

## API clients

### `src/api/http.ts`
Small fetch wrapper:
- Sends JSON automatically if `init.json` is provided
- Throws a readable error on non-2xx responses (includes response text when possible)

### `src/api/agent.ts`
`runAgent(baseUrl, req)` → `POST {baseUrl}/agent`
- Request: `{ query, max_steps, session_id }`
- Response: `AgentResponse`

### `src/api/advanced.ts`
`advancedMods(baseUrl, req)` → `POST {baseUrl}/advanced/mods`
- Present for server-side filtering/search (can be wired into UI later)

---

## Types

### `src/types/geojson.ts`
Lightweight GeoJSON types used across the app. (Mapbox GL’s TS types are stricter; `MapView` casts where needed.)

### `src/types/api.ts`
Types for backend payloads:
- `AgentRequest`, `AgentResponse`
- `OccurrenceInfo` (table rows + points)
- `AgentArtifacts` (geojson + spatial_geojson + spatial_buffer_geometry + csv)
- `AdvancedSearchRequest`, `AdvancedSearchResponse`

---

## UI (components)

### `src/ui/App.tsx`
Top-level UI shell:
- Loads runtime config (`loadAppConfig`) and stores it in Zustand
- Shows banners if config/token are missing
- Builds the **Kepler-like** resizable layout using `react-resizable-panels`:
  - left: `LayersPanel`
  - center: `MapView` (top) + `DataTablePanel` (bottom)
  - right: `ChatPanel` (collapsible)

Key UX detail:
- When the chat panel collapses/expands, the **map keeps state** (camera & layers do not reset).

### `src/ui/panels/ChatPanel.tsx`
Agent chat UI:
- Sends user text to `POST /agent` via `runAgent()`
- Writes chat messages to the store
- Applies agent outputs to the map + table via `applyAgentArtifacts()`:
  - `resp.occurrences` → `store.setOccurrences()` + `store.upsertDataset("agent-occurrences")`
  - `resp.artifacts.geojson` → `store.upsertDataset("agent-geojson")`
  - `resp.artifacts.spatial_geojson` → `store.upsertDataset("agent-spatial")`
  - `resp.artifacts.spatial_buffer_geometry` → `store.upsertDataset("agent-aoi")` (polygon, extruded)

UI details:
- Collapsible panel uses a chevron icon button
- Internal traces/plans are intentionally hidden from the user-facing chat UI

### `src/ui/panels/LayersPanel.tsx`
Layer control panel:
- Lists datasets from the store
- Toggle dataset visibility
- Set the active dataset
- Change styling:
  - Point mode: Scatter / Heatmap / Hexagon (3D)
  - Color / opacity / radius
  - Heatmap radius + intensity
  - Hex radius + elevation scale
  - Polygon extrusion + height

Map Settings:
- **Surface** selector: `Original | Satellite | Street`
  - `Original` uses `mapbox.style` from config
  - `Satellite` uses Mapbox satellite streets style
  - `Street` uses Mapbox streets style

### `src/ui/table/DataTablePanel.tsx`
Data table:
- Uses `@tanstack/react-table`
- Renders `store.occurrences`
- Row click → sets `store.map.selectedFeatureId`
- Highlights the selected row based on `selectedFeatureId`

### `src/ui/map/MapView.tsx`
Map implementation (core of visualization):

**Map initialization**
- Creates a single Mapbox map instance (stored in a ref) and does not re-create it on store changes.
- Adds terrain DEM source + `map.setTerrain()` and a “sky” layer for 3D feel.

**Basemap / Surface switching**
- When Surface changes, calls `map.setStyle(styleUrl)`.
- On `style.load`, re-attaches:
  - terrain + sky
  - dataset sources/layers

**Responsive resizing**
- Uses a `ResizeObserver` on the map container.
- Calls `map.resize()` when panels resize (chat collapse, table drag, etc).

**Rendering modes**
- **Scatter**: Mapbox `circle` layer per dataset.
- **Heatmap**: Mapbox `heatmap` layer per dataset.
- **Hexagon (3D)**: deck.gl `HexagonLayer` rendered via `MapboxOverlay`.

**Interactions**
- Click a point → updates `selectedFeatureId`
- Hover a point → popup tooltip (name/commodity/region)
- Selection highlight → separate `:selected` layer with a filter on `properties.id`

---

## Styling

### `src/styles/index.css`
App theme + shared component styles:
- Dark UI theme variables
- Panel/header/button/input styles
- Banners for missing config/token

### `src/index.css` and `src/App.css`
Default Vite template CSS (not used by the main app layout). The app uses `src/styles/index.css` instead.

---

## Extending the frontend (common tasks)

### Add a new dataset type
Add a new `store.upsertDataset()` call (usually inside `applyAgentArtifacts()` in `ChatPanel.tsx`) with:
- a unique `id`
- a `GeoJSONFeatureCollection` in `data`
- `kind` and default `style`

### Add a new visualization mode
1) Add an option in `DatasetLayer["style"].pointMode` (store type)
2) Add UI control in `LayersPanel.tsx`
3) Render it in `MapView.tsx`:
   - Mapbox layer if possible, or
   - deck.gl layer via `MapboxOverlay`

### Add streaming (SSE/WebSocket)
Current chat uses a single `POST /agent`. To stream:
- Add an SSE client in `src/api/agent.ts` (or a new `agentStream.ts`)
- In `ChatPanel.tsx`, append partial tokens to the last assistant message as they arrive

---

## Known build notes

During `vite build`, you may see a warning about `@loaders.gl/worker-utils` and `"spawn"` not being exported by `__vite-browser-external`. The build still succeeds; it’s coming from a dependency chain used by deck.gl.

