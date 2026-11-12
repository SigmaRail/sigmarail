import { chromium } from "@playwright/test";
const cdpUrl = process.env.CDP || "http://localhost:9222";
const action = process.env.ACTION || "inspect";
const expr = process.env.EXPR || "";
const selector = process.env.SEL || "";
const value = process.env.VAL || "";
const goto = process.env.GOTO || "";
const wait = process.env.WAIT || "0";
const browser = await chromium.connectOverCDP(cdpUrl);
const pages = browser.contexts().flatMap((c) => c.pages());
let page = pages.find((p) => p.url().includes("5174")) || pages[0];
const errs = [];
page.on("console", (m) => { if (m.type() === "error") errs.push("[console.error] " + m.text()); });
page.on("pageerror", (e) => errs.push("[pageerror] " + e.message));
if (goto) await page.goto(goto, { waitUntil: "domcontentloaded", timeout: 15000 });
if (wait !== "0") await page.waitForTimeout(Number(wait));
let out = { url: page.url() };
if (action === "inspect") {
  out.title = await page.title();
  out.body = (await page.locator("body").innerText()).slice(0, 1200);
} else if (action === "eval") {
  out.result = await page.evaluate(expr);
} else if (action === "click") {
  await page.click(selector, { timeout: 8000 });
  out.clicked = selector;
} else if (action === "fill") {
  await page.fill(selector, value, { timeout: 8000 });
  out.filled = selector;
} else if (action === "text") {
  out.text = await page.locator(selector).innerText({ timeout: 8000 });
} else if (action === "count") {
  out.count = await page.locator(selector).count();
}
out.errors = errs;
console.log(JSON.stringify(out, null, 2));
await browser.close();