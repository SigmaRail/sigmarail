import { chromium } from '@playwright/test';

const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
page.on('console', (msg) => {
  if (msg.type() === 'error' || msg.type() === 'warning') errors.push(`${msg.type()}: ${msg.text()}`);
});
page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`));
await page.goto('http://localhost:5173/optimize', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(6000);
const body = await page.locator('body').innerText().catch(() => '<no body>');
console.log('=== BODY (first 1500 chars) ===');
console.log(body.slice(0, 1500));
console.log('=== CONSOLE ERRORS ===');
for (const e of errors.slice(0, 20)) console.log(e);
await browser.close();
