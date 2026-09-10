import { chromium } from "playwright";
const BASE = "http://localhost:3000";
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const all = new Set(["/"]);
const visited = new Set();
const bad = [];

async function crawl(url) {
  if (visited.has(url)) return;
  visited.add(url);
  const res = await page.goto(BASE + url, { waitUntil: "domcontentloaded", timeout: 60000 });
  const status = res?.status() ?? 0;
  if (status >= 400) bad.push(`${url} -> ${status}`);
  const hrefs = await page.$$eval("a[href]", (as) => as.map((a) => a.getAttribute("href")));
  for (const h of hrefs) {
    if (!h) continue;
    if (h.startsWith("http") || h.startsWith("#") || h.startsWith("mailto:")) continue;
    if (h.startsWith("/")) all.add(h.split("#")[0] || "/");
  }
}
for (let i = 0; i < 6; i++) {
  const batch = [...all].filter((u) => !visited.has(u));
  if (!batch.length) break;
  for (const u of batch) await crawl(u);
}
console.log(`crawled ${visited.size} internal routes`);
console.log(bad.length ? "BROKEN:\n" + bad.join("\n") : "NO BROKEN INTERNAL LINKS");
await b.close();
