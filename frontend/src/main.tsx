import React from "react";
import ReactDOM from "react-dom/client";
import "mapbox-gl/dist/mapbox-gl.css";
import "./styles/index.css";
import { App } from "./ui/App";

// Entry point: mounts the UI app and loads global styles (including Mapbox CSS).
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
