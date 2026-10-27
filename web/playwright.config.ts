import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  workers: 1,
  use: { baseURL: "http://127.0.0.1:8766", trace: "retain-on-failure" },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["iPhone 13"],
        defaultBrowserType: "chromium",
        launchOptions: {
          executablePath: process.env.DESKPAD_CHROMIUM_EXECUTABLE || undefined,
        },
      },
    },
    { name: "webkit", use: { ...devices["iPhone 13"] } },
  ],
  webServer: {
    command: `${process.platform === "win32" ? "..\\.venv\\Scripts\\python.exe" : "../.venv/bin/python"} ../host/tests/browser_host.py`,
    url: "http://127.0.0.1:8766/api/status",
    reuseExistingServer: false,
  },
});
