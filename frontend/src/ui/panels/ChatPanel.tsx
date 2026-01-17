import { useMemo, useRef, useState } from "react";
import { runAgent } from "../../api/agent";
import { useAppStore } from "../../store/appStore";
import type { GeoJSONFeatureCollection } from "../../types/geojson";
import type { AgentResponse } from "../../types/api";

/**
 * ChatPanel
 *
 * Responsibilities:
 * - Provide a user-facing chat UI to the backend agent (`POST /agent`).
 * - Persist chat messages + session id in the global store.
 * - Apply agent outputs (occurrences + GeoJSON artifacts) into map/table state.
 *
 * Note: internal tool traces / plans are intentionally hidden from the UI.
 */
function nowId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function scrubAudioUrls(text: string): string {
  // Safety: never render audio data URLs/base64 in chat output, even if the backend or older UI code includes it.
  // - Removes any line starting with "Audio:" (case-insensitive)
  // - Removes any inline data:audio/... tokens if present
  if (!text) return text;
  const withoutAudioLines = text.replace(/^\s*audio:\s*.*$/gim, "").trim();
  const withoutInlineData = withoutAudioLines.replace(/data:audio\/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=]+/gi, "[audio]");
  return withoutInlineData.trim();
}

function occurrencesToFc(occurrences: any[]): GeoJSONFeatureCollection {
  return {
    type: "FeatureCollection",
    // Coerce lon/lat to numbers to avoid Mapbox silently dropping invalid coordinates.
    features: occurrences
      .map((o: any) => {
        const lon = typeof o?.longitude === "string" ? Number(o.longitude) : o?.longitude;
        const lat = typeof o?.latitude === "string" ? Number(o.latitude) : o?.latitude;
        if (!Number.isFinite(lon) || !Number.isFinite(lat)) return null;
        return {
          type: "Feature" as const,
          geometry: { type: "Point" as const, coordinates: [lon, lat] as any },
          properties: {
            id: o.mods_id ?? undefined,
            mods_id: o.mods_id,
            english_name: o.english_name,
            arabic_name: o.arabic_name,
            major_commodity: o.major_commodity,
            admin_region: o.admin_region,
            occurrence_type: o.occurrence_type,
            exploration_status: o.exploration_status,
            occurrence_importance: o.occurrence_importance,
          },
        };
      })
      .filter(Boolean) as any,
  };
}

function geomToFc(geom: any): GeoJSONFeatureCollection {
  return {
    type: "FeatureCollection",
    features: [{ type: "Feature", geometry: geom, properties: { id: "aoi" } }],
  };
}

function applyAgentArtifacts(resp: AgentResponse) {
  const { upsertDataset, setOccurrences, setSessionId, setLastArtifacts } = useAppStore.getState();

  // Keep backend session stable across prompts (enables conversational context server-side).
  if (resp.session_id) setSessionId(resp.session_id);

  // Store artifacts for other panels (charts/exports).
  setLastArtifacts(resp.artifacts ?? null);

  // If the agent returns occurrences, sync them into:
  // - the table (rows)
  // - a points dataset on the map
  const occs = resp.occurrences ?? [];
  setOccurrences(occs);
  if (occs.length) {
    upsertDataset({
      id: "agent-occurrences",
      name: "Agent → Occurrences",
      kind: "points",
      data: occurrencesToFc(occs),
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
  } else {
    // Clear the previous layer so the map doesn't show stale results.
    upsertDataset({
      id: "agent-occurrences",
      name: "Agent → Occurrences",
      kind: "points",
      data: { type: "FeatureCollection", features: [] },
      visible: false,
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
  }

  const a = resp.artifacts;
  // Agent may return arbitrary GeoJSON; normalize IDs for map selection/highlight.
  if (a?.geojson) {
    const normalized: GeoJSONFeatureCollection = {
      type: "FeatureCollection",
      features: a.geojson.features.map((f: any) => ({
        ...f,
        properties: { ...(f.properties ?? {}), id: f.properties?.mods_id ?? f.properties?.id ?? f.id },
      })),
    };
    upsertDataset({
      id: "agent-geojson",
      name: "Agent → GeoJSON",
      kind: "mixed",
      data: normalized,
      visible: true,
      style: {
        pointMode: "scatter",
        color: "#a78bfa",
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
  }
  if (a?.spatial_geojson) {
    const normalized: GeoJSONFeatureCollection = {
      type: "FeatureCollection",
      features: a.spatial_geojson.features.map((f: any) => ({
        ...f,
        properties: { ...(f.properties ?? {}), id: f.properties?.mods_id ?? f.properties?.id ?? f.id },
      })),
    };
    upsertDataset({
      id: "agent-spatial",
      name: "Agent → Spatial GeoJSON",
      kind: "mixed",
      data: normalized,
      visible: true,
      style: {
        pointMode: "scatter",
        color: "#fb7185",
        opacity: 0.65,
        radius: 5,
        heatmapRadius: 24,
        heatmapIntensity: 1,
        hexRadius: 7000,
        hexElevationScale: 25,
        extrude: false,
        extrudeHeight: 250,
      },
    });
  }
  if (a?.spatial_buffer_geometry) {
    // Buffer/AOI outputs are polygons; enable extrusion by default for 3D context.
    upsertDataset({
      id: "agent-aoi",
      name: "Agent → AOI / Buffer",
      kind: "polygon",
      data: geomToFc(a.spatial_buffer_geometry),
      visible: true,
      style: {
        pointMode: "scatter",
        color: "#f59e0b",
        opacity: 0.5,
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
}

function ChevronIcon({ direction }: { direction: "left" | "right" }) {
  const rotate = direction === "left" ? "180deg" : "0deg";
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" style={{ transform: `rotate(${rotate})` }} aria-hidden="true">
      <path
        fill="currentColor"
        d="M9.29 6.71a1 1 0 0 1 1.42 0L16 12l-5.29 5.29a1 1 0 1 1-1.42-1.42L13.17 12L9.29 8.12a1 1 0 0 1 0-1.41Z"
      />
    </svg>
  );
}

export function ChatPanel({ onCollapse, onExpand }: { onCollapse: () => void; onExpand: () => void }) {
  const config = useAppStore((s) => s.config);
  const chatCollapsed = useAppStore((s) => s.chatCollapsed);
  const setChatCollapsed = useAppStore((s) => s.setChatCollapsed);
  const sessionId = useAppStore((s) => s.sessionId);
  const messages = useAppStore((s) => s.chat.messages);
  const isBusy = useAppStore((s) => s.chat.isBusy);
  const pushMessage = useAppStore((s) => s.chat.pushMessage);
  const setBusy = useAppStore((s) => s.chat.setBusy);

  // Backend URL is runtime-configurable (public/config.json).
  // Default to same-origin. In dev, Vite proxies `/agent`, `/query`, etc to the FastAPI backend.
  const backendUrl = useMemo(() => config?.backendUrl ?? "", [config]);
  const [text, setText] = useState("");
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [audioBusy, setAudioBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordError, setRecordError] = useState<string | null>(null);
  const [recordPreviewUrl, setRecordPreviewUrl] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  async function send() {
    const q = text.trim();
    if (!q) return;
    setText("");
    const userMsgId = nowId();
    pushMessage({ id: userMsgId, role: "user", text: q, createdAt: Date.now() });

    setBusy(true);
    try {
      // Single request endpoint; backend does its own routing/tool selection.
      const resp = await runAgent(backendUrl, {
        query: q,
        max_steps: 3,
        session_id: sessionId,
      });
      applyAgentArtifacts(resp);
      pushMessage({
        id: nowId(),
        role: "assistant",
        text: scrubAudioUrls(resp.response),
        createdAt: Date.now(),
        toolTrace: resp.tool_trace,
      });
    } catch (e: any) {
      pushMessage({
        id: nowId(),
        role: "assistant",
        text: `ERROR: ${e?.message ?? String(e)}`,
        createdAt: Date.now(),
      });
    } finally {
      setBusy(false);
    }
  }

  async function sendAudio() {
    if (!audioFile) return;
    setAudioBusy(true);
    try {
      pushMessage({ id: nowId(), role: "user", text: `[Audio] ${audioFile.name}`, createdAt: Date.now() });

      const fd = new FormData();
      fd.append("audio", audioFile, audioFile.name);
      fd.append("return_audio_base64", "true");
      fd.append("voice", "ar-XA-Wavenet-B");
      fd.append("max_steps", "3");

      const b = backendUrl.replace(/\/$/, "");
      const res = await fetch(`${b}/speech/process`, { method: "POST", body: fd });
      const txt = await res.text().catch(() => "");
      if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText} @ ${b}/speech/process: ${txt}`.trim());
      const data = JSON.parse(txt);

      const ar = data?.arabic_text ?? "";
      const sttAr = data?.stt_arabic ?? "";
      const sttEn = data?.stt_english ?? "";
      const en = data?.agent_english ?? "";
      const audio64 = data?.audio_base64 ?? "";
      const audioUrl = audio64 ? `data:audio/mp3;base64,${audio64}` : "";

      // IMPORTANT: voice queries should populate the same UI state as typed queries.
      // /speech/process now returns { occurrences, artifacts, tool_trace } like /agent/.
      try {
        applyAgentArtifacts({
          response: String(en || ""),
          tool_trace: (data?.tool_trace ?? null) as any,
          occurrences: (data?.occurrences ?? null) as any,
          artifacts: (data?.artifacts ?? null) as any,
          session_id: null as any,
        } as AgentResponse);
      } catch {
        // If anything is missing/malformed, still show chat + audio.
      }

      pushMessage({
        id: nowId(),
        role: "assistant",
        // IMPORTANT: do not print the audio URL/base64 in chat; just auto-play it.
        text: scrubAudioUrls(
          `${ar}` +
            `${sttAr ? `\n\nTranscript (AR): ${sttAr}` : ""}` +
            `${!sttAr && sttEn ? `\n\nTranscript (EN): ${sttEn}` : ""}` +
            `\n\n(English: ${en})`
        ),
        createdAt: Date.now(),
      });

      // Auto-play through device speakers (browser permission dependent).
      if (audioUrl) {
        try {
          const a = new Audio(audioUrl);
          a.play().catch(() => {
            // Autoplay may be blocked; user can still open the Audio: data URL.
          });
        } catch {
          // ignore
        }
      }

      setAudioFile(null);
      setRecordPreviewUrl(null);
    } catch (e: any) {
      pushMessage({ id: nowId(), role: "assistant", text: `ERROR (speech): ${e?.message ?? String(e)}`, createdAt: Date.now() });
    } finally {
      setAudioBusy(false);
    }
  }

  async function startRecording() {
    setRecordError(null);
    setRecordPreviewUrl(null);
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("Microphone is not supported in this browser.");
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;

      chunksRef.current = [];
      const rec = new MediaRecorder(stream);
      mediaRecorderRef.current = rec;
      rec.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: rec.mimeType || "audio/webm" });
        const url = URL.createObjectURL(blob);
        setRecordPreviewUrl(url);
        // Use .webm by default; Whisper can decode via ffmpeg on the server.
        const file = new File([blob], `mic-${Date.now()}.webm`, { type: blob.type });
        setAudioFile(file);
      };

      rec.start();
      setRecording(true);
    } catch (e: any) {
      setRecordError(e?.message ?? String(e));
      setRecording(false);
      try {
        mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
      } catch {
        // ignore
      }
      mediaStreamRef.current = null;
    }
  }

  function stopRecording() {
    try {
      mediaRecorderRef.current?.stop();
    } catch {
      // ignore
    }
    try {
      mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    } catch {
      // ignore
    }
    mediaStreamRef.current = null;
    setRecording(false);
  }

  if (chatCollapsed) {
    return (
      <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
        <div className="panelHeader" style={{ justifyContent: "center" }}>
          <button
            className="btn"
            title="Open chat"
            aria-label="Open chat"
            onClick={() => {
              setChatCollapsed(false);
              onExpand();
            }}
          >
            <ChevronIcon direction="left" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div className="panelHeader">
        <div>
          <div className="panelTitle">Agent Chat</div>
        </div>
        <button
          className="btn"
          title="Collapse chat"
          aria-label="Collapse chat"
          onClick={() => {
            setChatCollapsed(true);
            onCollapse();
          }}
        >
          <ChevronIcon direction="right" />
        </button>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
        {messages.length === 0 && (
          <div className="muted" style={{ fontSize: 13 }}>
            Try: “Show me gold occurrences in Riyadh”, or “Create a 10km buffer around my last AOI and list nearest
            occurrences.”
          </div>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            style={{
              alignSelf: m.role === "user" ? "flex-end" : "flex-start",
              maxWidth: "92%",
              border: "1px solid var(--border)",
              borderRadius: 14,
              padding: "10px 12px",
              background: m.role === "user" ? "rgba(34,197,94,0.08)" : "rgba(255,255,255,0.03)",
            }}
          >
            <div style={{ fontSize: 13, whiteSpace: "pre-wrap" }}>{m.text}</div>
            {/* intentionally hide tool traces / plans from the user-facing chat UI */}
          </div>
        ))}
        {isBusy && (
          <div className="muted" style={{ fontSize: 13 }}>
            Agent is working…
          </div>
        )}
      </div>

      <div style={{ padding: 12, borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            className="input"
            placeholder="Ask the agent…"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
          />
          <button className="btn btnPrimary" onClick={send} disabled={isBusy}>
            Send
          </button>
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button className="btn" onClick={recording ? stopRecording : startRecording} disabled={audioBusy}>
            {recording ? "Stop Mic" : "Record Mic"}
          </button>
          <button className="btn" onClick={sendAudio} disabled={audioBusy || !audioFile}>
            {audioBusy ? "Processing…" : "Send Audio"}
          </button>
        </div>
        {recordError && (
          <div className="muted" style={{ fontSize: 12 }}>
            Mic error: {recordError}
          </div>
        )}
        {recordPreviewUrl && (
          <audio controls src={recordPreviewUrl} style={{ width: "100%" }} />
        )}
      </div>
    </div>
  );
}

