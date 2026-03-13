/**
 * main.tsx — admin portal entry point.
 *
 * Mounts the App component into #root.
 * CSS is imported here so Vite bundles it with this entry point.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("Root element #root not found");

createRoot(rootEl).render(
  <StrictMode>
    <App />
  </StrictMode>
);
