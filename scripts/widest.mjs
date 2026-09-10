import { chromium } from "playwright";
const b = await chromium.launch();
for (const route of ["/", "/reporter"]) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 } });
  const p = await ctx.newPage();
  await p.goto("http://localhost:3000" + route, { waitUntil: "networkidle" });
  await p.waitForTimeout(800);
  const res = await p.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const rows = [];
    document.querySelectorAll("*").forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.width > vw + 1) {
        rows.push({
          tag: el.tagName.toLowerCase(),
          cls: (el.className || "").toString().slice(0, 70),
          w: Math.round(r.width),
          left: Math.round(r.left),
          text: (el.textContent || "").trim().slice(0, 40),
          childCount: el.children.length,
        });
      }
    });
    return rows.slice(0, 14);
  });
  console.log("\n=== " + route + " ===");
  res.forEach((r) => console.log(`${r.w}px  <${r.tag}> [${r.cls}] kids=${r.childCount} "${r.text}"`));
  await ctx.close();
}
await b.close();
