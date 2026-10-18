import "@fontsource/onest/cyrillic-400.css";
import "@fontsource/onest/cyrillic-600.css";
import "@fontsource/onest/cyrillic-800.css";
import "@fontsource/onest/latin-400.css";
import "@fontsource/onest/latin-600.css";
import "@fontsource/onest/latin-800.css";
import "@fontsource/jetbrains-mono/latin-500.css";
import "./styles/tokens.css";
import "./styles/app.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
