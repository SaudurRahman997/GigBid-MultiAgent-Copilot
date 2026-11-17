import { mkdirSync } from "node:fs";
import { defineConfig, devices } from "@playwright/test";

// E2E specs (e2e/*.spec.ts). By default Playwright starts an isolated stack: the API in single-process
// demo mode (in-process tools, fresh SQLite) on :8010 and a production build of the web on :3010.
// Set BASE_URL to run the same specs against docker compose or the deployed site instead.
const external = process.env.BASE_URL;
mkdirSync("../../var", { recursive: true }); // gitignored, so missing on a fresh CI checkout
const db = `sqlite:///./var/e2e-${Date.now()}.db`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: external ?? "http://localhost:3010",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: external
    ? undefined
    : [
        {
          command: "uv run uvicorn apps.api.main:app --port 8010",
          cwd: "../..",
          url: "http://localhost:8010/health",
          timeout: 120_000,
          reuseExistingServer: false,
          env: { GIGBID_MCP_MODE: "inprocess", GIGBID_AGENT_MODE: "rules", API_DATABASE_URL: db },
        },
        {
          command: "npm run build && npx next start -p 3010",
          url: "http://localhost:3010/onboarding",
          timeout: 300_000,
          reuseExistingServer: false,
          env: { NEXT_PUBLIC_API_URL: "/api", API_INTERNAL_URL: "http://127.0.0.1:8010" },
        },
      ],
});
