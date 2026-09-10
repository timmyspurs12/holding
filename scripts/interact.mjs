import { chromium } from "playwright";

const BASE = "http://localhost:3000";
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const errs = [];
page.on("pageerror", (e) => errs.push("pageerror: " + e.message.slice(0, 160)));
page.on("console", (m) => {
  if (m.type() === "error") errs.push("console: " + m.text().slice(0, 160));
});

const results = [];
const check = (name, ok, detail = "") =>
  results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? " — " + detail : ""}`);

/* 1 · distinguishment demo on the landing page */
await page.goto(BASE + "/", { waitUntil: "networkidle" });
await page.getByRole("button", { name: /why different/i }).click({ timeout: 15000 });
await page.waitForTimeout(900);
check(
  "distinguishment reveals the material difference",
  await page.getByText(/Unlike Holding #00184/i).first().isVisible(),
);
await page.waitForTimeout(4200);
check(
  "distinguishment completes to a new holding",
  await page.getByText(/Holding #00417/i).first().isVisible(),
);

/* 2 · live demo steps */
const stepBtn = page.getByRole("button", { name: /^09 Consensus$/ });
if (await stepBtn.count()) {
  await stepBtn.first().click();
  await page.waitForTimeout(4500);
  check("live demo jumps to consensus stage", await page.getByText(/Followed/i).first().isVisible());
} else {
  check("live demo step rail present", false, "step 09 button not found");
}

/* 3 · reporter search + filter */
await page.goto(BASE + "/reporter", { waitUntil: "networkidle" });
const before = await page.locator("a[href^='/holdings/']").count();
await page.getByPlaceholder(/Search holdings/i).fill("refund");
await page.waitForTimeout(900);
const after = await page.locator("a[href^='/holdings/']").count();
check("reporter search filters results", after > 0 && after < before, `${before} -> ${after}`);
await page.getByPlaceholder(/Search holdings/i).fill("zzzzz");
await page.waitForTimeout(800);
check("reporter empty state renders", await page.getByText(/No holdings match/i).isVisible());
await page.getByRole("button", { name: /Clear filters/i }).first().click();
await page.waitForTimeout(600);
check("clear filters restores results", (await page.locator("a[href^='/holdings/']").count()) > 0);

/* 4 · precedent console */
await page.goto(BASE + "/precedent", { waitUntil: "networkidle" });
await page.getByRole("button", { name: /Run the panel/i }).click();
await page.waitForTimeout(6000);
check("precedent console reaches a verdict", await page.getByText(/APPROVED|REJECTED|PARTIAL/i).first().isVisible());
await page.getByRole("button", { name: /Full delivery before cancellation/i }).click();
await page.waitForTimeout(400);
check("scenario switch resets the console", await page.getByRole("button", { name: /Run the panel/i }).isVisible());

/* 5 · holding detail: evidence accordion + citation map */
await page.goto(BASE + "/holdings/00184", { waitUntil: "networkidle" });
await page.getByRole("button", { name: /Usage log extract/i }).click();
await page.waitForTimeout(600);
check("evidence accordion expands", await page.getByText(/Recorded hash/i).first().isVisible());
check("citation map renders nodes", (await page.locator("svg circle").count()) > 3);

/* 6 · keyboard navigation */
await page.goto(BASE + "/", { waitUntil: "networkidle" });
await page.keyboard.press("Tab");
const focusChain = new Set();
for (let i = 0; i < 12; i++) {
  focusChain.add(await page.evaluate(() => document.activeElement?.tagName || "none"));
  await page.keyboard.press("Tab");
}
check("keyboard focus moves through interactive elements", focusChain.has("A") || focusChain.has("BUTTON"));

console.log(results.join("\n"));
console.log(errs.length ? "\nCONSOLE/PAGE ERRORS:\n" + errs.join("\n") : "\nNO CONSOLE ERRORS");
await b.close();
