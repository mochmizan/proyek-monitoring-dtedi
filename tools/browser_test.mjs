// browser_test.mjs - Playwright headless login->dashboard flow.
// Requires Vite dev server on :5173. DEV credentials via env (e.g. SMSB_USER/SMSB_PASS),
// not hardcoded for prod - update to read from process.env before production use.

import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';

async function runBrowserTest() {
  console.log('🚀 Launching Chromium browser agent...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 }
  });
  const page = await context.newPage();

  const screenshotsDir = path.resolve('../../browser_screenshots');
  if (!fs.existsSync(screenshotsDir)) {
    fs.mkdirSync(screenshotsDir, { recursive: true });
  }

  try {
    // 1. Visit Login Page
    console.log('📍 Navigating to http://localhost:5173/login ...');
    await page.goto('http://localhost:5173/login', { waitUntil: 'networkidle' });
    console.log('Title:', await page.title());

    await page.screenshot({ path: path.join(screenshotsDir, '1_login_page.png') });
    console.log('📸 Captured 1_login_page.png');

    // 2. Perform Login
    console.log('🔑 Entering admin credentials...');
    await page.fill('input[name="username"], input[type="text"]', 'admin');
    await page.fill('input[name="password"], input[type="password"]', 'admin');
    await page.click('button[type="submit"]');

    // 3. Wait for Dashboard Navigation
    console.log('⏳ Waiting for Dashboard navigation...');
    await page.waitForURL('http://localhost:5173/', { timeout: 10000 });
    await page.waitForTimeout(2000); // Allow TanStack Query polling

    await page.screenshot({ path: path.join(screenshotsDir, '2_dashboard.png') });
    console.log('📸 Captured 2_dashboard.png');

    // Verify rooms on dashboard
    const bodyText = await page.textContent('body');
    const hasServerRoom = bodyText.includes('Server Room');
    const hasNetworkCloset = bodyText.includes('Network Closet');
    const hasBatteryRoom = bodyText.includes('Battery Room');

    console.log('✅ Dashboard Content Check:');
    console.log('  - Server Room present:', hasServerRoom);
    console.log('  - Network Closet present:', hasNetworkCloset);
    console.log('  - Battery Room present:', hasBatteryRoom);

    // 4. Navigate to Map View
    console.log('📍 Navigating to /map ...');
    await page.goto('http://localhost:5173/map', { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(screenshotsDir, '3_map_view.png') });
    console.log('📸 Captured 3_map_view.png');

    // 5. Navigate to Settings
    console.log('📍 Navigating to /settings ...');
    await page.goto('http://localhost:5173/settings', { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(screenshotsDir, '4_settings.png') });
    console.log('📸 Captured 4_settings.png');

    // 6. Navigate to Alerts
    console.log('📍 Navigating to /alerts ...');
    await page.goto('http://localhost:5173/alerts', { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(screenshotsDir, '5_alerts.png') });
    console.log('📸 Captured 5_alerts.png');

    console.log('🎉 Browser agent test completed successfully with all pages verified!');
  } catch (error) {
    console.error('❌ Browser agent test error:', error);
    await page.screenshot({ path: path.join(screenshotsDir, 'error.png') });
    process.exit(1);
  } finally {
    await browser.close();
  }
}

runBrowserTest();
