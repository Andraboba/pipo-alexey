import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Сборка кладётся в ../web/dist, FastAPI раздаёт её по /static/.
// Для разработки: запустите бэкенд с PIPO_TOKEN=dev, а фронт — `npm run dev`
// с VITE_PIPO_TOKEN=dev; запросы /api проксируются на бэкенд.
export default defineConfig({
  plugins: [react()],
  base: "/static/",
  build: { outDir: "../web/dist", emptyOutDir: true },
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:47800" },
  },
});
