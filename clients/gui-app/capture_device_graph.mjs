import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';

async function captureDeviceGraph() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await context.newPage();

  const screenshotsDir = path.resolve('../../browser_screenshots');
  if (!fs.existsSync(screenshotsDir)) {
    fs.mkdirSync(screenshotsDir, { recursive: true });
  }

  try {
    // 1. Login
    await page.goto('http://localhost:5173/login', { waitUntil: 'networkidle' });
    await page.fill('input[type="text"]', 'admin');
    await page.fill('input[type="password"]', 'admin');
    await page.click('button[type="submit"]');
    await page.waitForURL('http://localhost:5173/', { timeout: 10000 });

    // 2. Navigate to Device Detail
    const deviceUrl = 'http://localhost:5173/device/AA:BB:CC:11:22:01';
    console.log('Navigating to', deviceUrl);
    await page.goto(deviceUrl, { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);

    const screenshotPath = path.join(screenshotsDir, '6_device_graph.png');
    await page.screenshot({ path: screenshotPath });
    console.log('📸 Captured 6_device_graph.png');

    // Also copy to artifact dir
    const artifactPath = 'C:\\Users\\Mizan\\.gemini\\antigravity\\brain\\5b4e154c-a0b0-4594-a0b1-d6279579a304\\6_device_graph.png';
    fs.copyFileSync(screenshotPath, artifactPath);
    console.log('📸 Copied to artifact directory');
  } catch (err) {
    console.error('Error capturing device graph:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

captureDeviceGraph();
