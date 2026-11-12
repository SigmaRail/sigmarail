#!/usr/bin/env node
import { chromium } from '@playwright/test';

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith('--')) continue;
    const key = token.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith('--')) {
      out[key] = true;
      continue;
    }
    out[key] = next;
    i += 1;
  }
  return out;
}

function fail(message, extra = {}) {
  console.error(JSON.stringify({ ok: false, error: message, ...extra }, null, 2));
  process.exit(1);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cdpUrl = args['cdp-url'];
  const wsEndpoint = args['ws-endpoint'];
  const action = String(args.action || 'inspect');
  const pageUrlFilter = args.url ? String(args.url) : null;
  const selector = args.selector ? String(args.selector) : null;
  const value = args.value ? String(args.value) : null;
  const gotoUrl = args.goto ? String(args.goto) : null;
  const textSelector = args['text-selector'] ? String(args['text-selector']) : null;
  const timeout = Number(args.timeout || 10000);

  if (!cdpUrl && !wsEndpoint) {
    fail('Provide --cdp-url or --ws-endpoint');
  }

  const browser = cdpUrl
    ? await chromium.connectOverCDP(cdpUrl)
    : await chromium.connect(wsEndpoint);

  try {
    const contexts = browser.contexts();
    const pages = contexts.flatMap((context) => context.pages());
    let page = pages[0] || null;

    if (pageUrlFilter) {
      page = pages.find((p) => p.url().includes(pageUrlFilter)) || page;
    }

    if (!page) {
      fail('No pages available in attached browser', { contexts: contexts.length, pages: 0 });
    }

    if (gotoUrl) {
      await page.goto(gotoUrl, { waitUntil: 'domcontentloaded', timeout });
    }

    let payload = { ok: true, action, pageUrl: page.url(), pages: pages.map((p) => p.url()) };

    if (action === 'inspect') {
      payload.title = await page.title();
    } else if (action === 'click') {
      if (!selector) fail('click requires --selector');
      await page.click(selector, { timeout });
    } else if (action === 'fill') {
      if (!selector) fail('fill requires --selector');
      await page.fill(selector, value ?? '', { timeout });
    } else if (action === 'text') {
      const target = textSelector || selector;
      if (!target) fail('text requires --selector or --text-selector');
      payload.text = await page.textContent(target, { timeout });
    } else if (action === 'html') {
      const target = selector || 'body';
      payload.html = await page.locator(target).innerHTML({ timeout });
    } else if (action === 'eval') {
      const expression = args.expression ? String(args.expression) : null;
      if (!expression) fail('eval requires --expression');
      payload.result = await page.evaluate(expression);
    } else {
      fail(`Unsupported action: ${action}`);
    }

    console.log(JSON.stringify(payload, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  fail(error instanceof Error ? error.message : String(error));
});
