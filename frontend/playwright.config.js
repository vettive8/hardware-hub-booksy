import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  forbidOnly: true,
  reporter: [['line'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  outputDir: 'test-results',
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:8001',
    channel: 'msedge',
    headless: process.env.PLAYWRIGHT_HEADLESS === '1',
    launchOptions: { slowMo: Number(process.env.PLAYWRIGHT_LIVE_SLOWMO || 0) },
    trace: 'on',
    video: 'on',
    screenshot: 'on',
  },
})
