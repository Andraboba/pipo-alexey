import { defineConfig } from "@playwright/test";

// UI-тесты: интерфейс из vite dev-сервера, API подменяется фикстурами (tests/ui/fixtures.json),
// поэтому не нужны ни бэкенд, ни права администратора, ни сам запрет.
// Браузер — установленный Edge: тот же движок, что WebView2 в окне приложения.
const PORT = 5174;

export default defineConfig({
  testDir: "tests/ui",
  fullyParallel: true,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${PORT}/static/`,
    channel: "msedge",
    viewport: { width: 1360, height: 900 },
  },
  webServer: {
    command: `npx vite --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}/static/`,
    reuseExistingServer: !process.env.CI,
  },
});
