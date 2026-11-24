// Базовые стили импортируются первыми: стили страниц должны идти после них в сборке
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/layout.css";
import "./styles/controls.css";
// масштаб применяется до первой отрисовки, чтобы окно не «прыгало»
import "./lib/uiScale.js";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import { ToastProvider } from "./ui/Toasts.jsx";
import { ConfirmProvider } from "./ui/ConfirmDialog.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <ToastProvider>
      <ConfirmProvider>
        <App />
      </ConfirmProvider>
    </ToastProvider>
  </StrictMode>,
);
