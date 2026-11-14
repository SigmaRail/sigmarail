import { expect, test } from "@playwright/test";

for (const device of [
  { name: "phone", width: 390, height: 844, hasTouch: true },
  { name: "portrait tablet", width: 768, height: 1024, hasTouch: true },
  { name: "landscape tablet", width: 1024, height: 768, hasTouch: true },
  { name: "desktop", width: 1440, height: 900, hasTouch: false },
]) {
  test.describe(device.name, () => {
    test.use({ viewport: { width: device.width, height: device.height }, hasTouch: device.hasTouch });
    test("navigates the lifecycle and restores a strategy slot", async ({ page }) => {
      const errors: string[] = [];
      page.on("pageerror", error => errors.push(error.message));
      await page.route("**/api/**", route => {
        const path = new URL(route.request().url()).pathname;
        if (!path.startsWith("/api/")) return route.continue();
        if (path === "/api/backtests/runs") return route.fulfill({ json: { runs: [
          { run_id: "older", ir_id: "research-one", ir_content_hash: "old" },
          { run_id: "pinned", ir_id: "research-one", ir_content_hash: "abc12345" },
        ] } });
        const body = path === "/api/backtests/specs/research-one"
          ? { ir_id: "research-one", title: "Research One", spec: {}, ir_content_hash: "abc12345",
              pipeline_document: { strategy_name: "Research One", stages: [] } }
          : {};
        return route.fulfill({ json: body });
      });
      await page.goto("/strategies/research-one?slot=alpha");
      const slots = page.getByRole("navigation", { name: "Strategy slots" });
      const currentSlot = slots.locator('[aria-current="page"]');
      await expect(currentSlot).toHaveText("Alpha");
      await expect(page.getByPlaceholder("Strategy name")).toHaveValue("Research One");
      await expect(page.getByRole("link", { name: "Inspect dated run pinned" })).toHaveAttribute("href", "/backtests/pinned/scrubber");
      await page.getByPlaceholder("Strategy name").fill("Edited title");
      for (const label of ["Universe", "Portfolio Construction", "Risk Management", "Execution"]) {
        const link = slots.getByRole("link", { name: label, exact: true });
        if (device.hasTouch) await link.tap(); else await link.click();
        await expect(currentSlot).toHaveText(label);
        await expect(page.getByRole("region", { name: label, exact: true })).toBeVisible();
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
        expect(overflow).toBe(false);
      }
      const executionChoice = page.getByRole("button", { name: "MOC (close of T)" });
      await executionChoice.click();
      await expect(executionChoice).toHaveAttribute("aria-pressed", "true");
      if (device.hasTouch) {
        await page.setViewportSize({ width: device.height, height: device.width });
        await expect(executionChoice).toHaveAttribute("aria-pressed", "true");
        await expect(currentSlot).toHaveText("Execution");
        await page.setViewportSize({ width: device.width, height: device.height });
      }
      await expect(page.getByPlaceholder("Strategy name")).toHaveValue("Edited title");
      await page.goBack();
      await expect(currentSlot).toHaveText("Risk Management");
      await page.goForward();
      await expect(currentSlot).toHaveText("Execution");
      await page.reload();
      await expect(currentSlot).toHaveText("Execution");
      if (device.width < 1024) {
        const trigger = page.getByRole("button", { name: "Open navigation" });
        await trigger.tap();
        const drawer = page.getByRole("dialog", { name: "Navigation" });
        await expect(drawer).toBeVisible();
        await page.keyboard.press("Escape");
        await expect(trigger).toBeFocused();
        await trigger.tap();
        await drawer.getByRole("link", { name: "Monitor", exact: true }).tap();
        await expect(drawer).toBeHidden();
        await trigger.tap();
        await drawer.getByRole("link", { name: "Strategies" }).tap();
        await page.setViewportSize({ width: device.height, height: device.width });
      } else {
        const nav = page.getByRole("navigation", { name: "Workbench lifecycle" });
        await page.getByRole("button", { name: /^(Expand|Collapse) navigation$/ }).click();
        await expect(nav.getByRole("link", { name: "Strategies" })).toHaveAttribute("aria-current", "page");
        await nav.getByRole("link", { name: "Monitor", exact: true }).click();
        await nav.getByRole("link", { name: "Strategies" }).click();
      }
      await expect(page).toHaveURL(/\/strategies\/research-one\?slot=execution$/);
      await expect(currentSlot).toHaveText("Execution");
      expect(errors).toEqual([]);
    });
  });
}

test.describe("phone destinations", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });
  test("reaches every destination and restores dated stock and deployment URLs", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", err => errors.push(err.message));
    await page.route("**/api/**", route => {
      const path = new URL(route.request().url()).pathname;
      if (!path.startsWith("/api/")) return route.continue();
      if (path === "/api/live/deployments") {
        return route.fulfill({ json: { deployments: [{ deployment_id: "paper-21", ir_id: "research-one", mode: "paper" }] } });
      }
      return route.fulfill({ json: {} });
    });
    await page.goto("/stock/UBER/chart?as_of=2026-09-14");
    const menu = page.getByRole("button", { name: "Open navigation" });
    const drawer = page.getByRole("dialog", { name: "Navigation" });
    for (const name of ["Screens", "Watchlists", "Market", "Strategies", "Backtests", "Optimize", "Deploy", "Monitor", "Charts"]) {
      await menu.tap();
      await drawer.getByRole("link", { name, exact: true }).tap();
      await expect(drawer).toBeHidden();
      await expect(page.locator(".workbench-header")).toContainText(name);
      const overflow = await page.evaluate(() => {
        const content = document.querySelector(".workbench > div > main")!;
        return Math.max(document.documentElement.scrollWidth - innerWidth, content.scrollWidth - content.clientWidth);
      });
      expect(overflow, name).toBeLessThanOrEqual(1);
    }
    await expect(page).toHaveURL(/\/stock\/UBER\/chart\?as_of=2026-09-14$/);
    await page.goto("/deploy?deployment=paper-21");
    await page.reload();
    await expect(page).toHaveURL(/deployment=paper-21/);
    expect(errors).toEqual([]);
  });
});

test("keeps a dated saved screen through refresh and browser history", async ({ page }) => {
  const spec = { version: "universe_query_v1", where: { type: "and", items: [] }, limit_per_day: 25 };
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith("/api/")) return route.continue();
    if (path === "/api/screens/saved") return route.fulfill({ json: { screens: [{ id: 12, name: "Research screen", spec }] } });
    return route.fulfill({ json: {} });
  });
  await page.goto("/screens?screen=12&as_of=2026-09-14&view=grid");
  const date = page.locator('input[type=date]').first();
  await expect(date).toHaveValue("2026-09-14");
  await date.fill("2026-09-16");
  await expect(page).toHaveURL(/as_of=2026-09-16/);
  await page.goBack();
  await expect(date).toHaveValue("2026-09-14");
  await page.reload();
  await expect(page).toHaveURL(/screen=12/);
  await expect(page).toHaveURL(/view=grid/);
  await expect(date).toHaveValue("2026-09-14");
});

test("starts a new draft directly in Execution and keeps the user's first edit", async ({ page }) => {
  await page.route("**/api/**", route => new URL(route.request().url()).pathname.startsWith("/api/")
    ? route.fulfill({ json: {} }) : route.continue());
  await page.goto("/strategies?slot=execution");
  const moc = page.getByRole("button", { name: "MOC (close of T)" });
  await moc.click();
  await page.getByRole("link", { name: "Alpha", exact: true }).click();
  await page.goBack();
  await expect(moc).toHaveAttribute("aria-pressed", "true");
});

test("switches saved strategies and resumes each strategy's edited slots", async ({ page }) => {
  const library = ["One", "Two"].map(title => ({
    ir_id: title.toLowerCase(), title, ir_content_hash: title + "-hash",
    has_pipeline: true, spec: {}, pipeline_document: { strategy_name: title, stages: [] },
  }));
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith("/api/")) return route.continue();
    if (path === "/api/backtests/specs") return route.fulfill({ json: { specs: library } });
    const detail = library.find(spec => path === "/api/backtests/specs/" + spec.ir_id);
    return route.fulfill({ json: detail ?? {} });
  });
  await page.goto("/strategies/one?slot=execution");
  const name = page.getByPlaceholder("Strategy name");
  await expect(name).toHaveValue("One");
  await name.fill("One draft");
  await page.getByRole("button", { name: "MOC (close of T)" }).click();
  await page.getByRole("button", { name: /Browse Specs/ }).click();
  await page.getByPlaceholder(/Search title/).fill("Two");
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await expect(name).toHaveValue("Two");
  await expect(page).toHaveURL(/\/two\?slot=execution/);
  await page.goBack();
  await expect(name).toHaveValue("One draft");
  await expect(page.getByRole("button", { name: "MOC (close of T)" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("Unsaved edits", { exact: true })).toBeVisible();
});
