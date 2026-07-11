import { defineConfig, devices } from '@playwright/test'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendDir = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.resolve(frontendDir, '..')
const backendDir = path.join(projectRoot, 'backend')
const pythonExecutable = process.platform === 'win32'
  ? path.join(backendDir, '.venv', 'Scripts', 'python.exe')
  : path.join(backendDir, '.venv', 'bin', 'python')
const baseURL = 'http://127.0.0.1:8765'

export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 5_000 },
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], channel: 'chrome' },
    },
  ],
  webServer: {
    command: `"${pythonExecutable}" -m uvicorn app.main:create_default_app --factory --host 127.0.0.1 --port 8765`,
    cwd: backendDir,
    env: {
      SEMIREVIEW_DATA_DIR: path.join(tmpdir(), `semiconductor-review-e2e-${process.pid}-${Date.now()}`),
      SEMIREVIEW_FRONTEND_DIST: path.join(frontendDir, 'dist'),
    },
    url: `${baseURL}/ready`,
    reuseExistingServer: false,
    timeout: 30_000,
  },
})
