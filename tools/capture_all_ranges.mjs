import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';

async function captureAllRanges() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await context.newPage();

  const screenshotsDir = path.resolve('../../browser_screenshots');
  if (!fs.existsSync(screenshotsDir)) {
    fs.mkdirSync(screenshotsDir, { recursive: true });
  }

  try {
    // Login
    await page.goto('http://localhost:5173/login', { waitUntil: 'networkidle' });
    await page.fill('input[type="text"]', 'admin');
    await page.fill('input[type="password"]', 'admin');
    await page.click('button[type="submit"]');
    await page.waitForURL('http://localhost:5173/', { timeout: 10000 });

    // Navigate to Device Detail
    const deviceUrl = 'http://localhost:5173/device/AA:BB:CC:11:22:01';
    await page.goto(deviceUrl, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);

    for (const range of ['6h', '24h', '7d', '30d']) {
      console.log(`Clicking ${range} button...`);
      // Find button with exact text
      await page.click(`button:has-text("${range}")`);
      await page.waitForTimeout(1500); // allow TanStack Query refetch
      const scrPath = path.join(screenshotsDir, `range_${range}.png`);
      await page.screenshot({ path: scrPath });
      console.log(`📸 Captured range_${range}.png`);
    }
  } catch (err) {
    console.error('Error capturing ranges:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

captureAllRanges();
