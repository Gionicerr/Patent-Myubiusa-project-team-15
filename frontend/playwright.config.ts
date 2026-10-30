import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './e2e', fullyParallel: false, workers: 1,
  reporter: 'list',
  use: { headless: true, launchOptions: {
    executablePath: process.env['CHROME_BIN'] || undefined,
    args: ['--no-sandbox', '--disable-dev-shm-usage']
  } },
  webServer: [
    { command: 'npm run start:mock -- --host 127.0.0.1 --port 4200', url: 'http://127.0.0.1:4200', reuseExistingServer: false, timeout: 120000 },
    { command: 'npm start -- --host 127.0.0.1 --port 4201', url: 'http://127.0.0.1:4201', env: { NOTES_API_URL: 'http://127.0.0.1:9' }, reuseExistingServer: false, timeout: 120000 }
  ]
});
