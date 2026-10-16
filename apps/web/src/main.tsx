/* SPDX-FileCopyrightText: 2026 BidWeave contributors
 * SPDX-License-Identifier: Apache-2.0
 * React entrypoint for the public landing page and PKCE workspace.
 */
import "@fontsource-variable/newsreader/index.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AuthProvider } from "./auth";
import { App } from "./App";

const root = document.getElementById("root");
if (!root) throw new Error("BidWeave root element is missing");
createRoot(root).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
);
