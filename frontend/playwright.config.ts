import { defineConfig, devices } from '@playwright/test';

const PORT = 8181;
/** Serves the fixture pages the URL import reads. */
const PAGES_PORT = 8182;

export default defineConfig({
  testDir: './e2e',
  // One worker, in file order. These tests share one backend and one database, and
  // claiming an instance is a one-way door — the bootstrap page only exists once.
  workers: 1,
  fullyParallel: false,
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'retain-on-failure',
    // The phone is the design target (NFR-11), so it is what the suite runs on.
    ...devices['Pixel 7'],
  },
  webServer: [
    {
      command: 'bash e2e/serve.sh',
      url: `http://127.0.0.1:${PORT}/api/v1/status`,
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      // Pages for the URL import to read. The fetch happens on the *server*, so
      // intercepting it in the browser would intercept nothing — these have to be really
      // served, and really fetched.
      command: `python3 -m http.server ${PAGES_PORT} --bind 127.0.0.1 --directory e2e/pages`,
      url: `http://127.0.0.1:${PAGES_PORT}/waffles.html`,
      timeout: 30_000,
      reuseExistingServer: false,
    },
  ],
});
