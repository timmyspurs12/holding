import { chromium } from "playwright";
const routes = ["/", "/reporter", "/holdings/00184", "/cases/0417", "/precedent", "/domains", "/developers", "/about", "/integrations", "/holdings", "/cases"];
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();

const script = () => {
  const lum = (c) => {
    const [r, g, bb] = c.map((v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * bb;
  };
  const parse = (s) => (s.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
  const bgOf = (el) => {
    let n = el;
    while (n && n !== document.documentElement) {
      const c = getComputedStyle(n).backgroundColor;
      const p = parse(c);
      const alpha = (c.match(/[\d.]+/g) || [])[3];
      if (p.length === 3 && (alpha === undefined || Number(alpha) > 0.85)) return p;
      n = n.parentElement;
    }
    return [10, 11, 13];
  };
  const out = [];
  document.querySelectorAll("*").forEach((el) => {
    if (el.children.length) return;
    const t = (el.textContent || "").trim();
    if (!t) return;
    const st = getComputedStyle(el);
    if (st.visibility === "hidden" || st.opacity === "0") return;
    const fg = parse(st.color);
    const bg = bgOf(el);
    const L1 = lum(fg), L2 = lum(bg);
    const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const size = parseFloat(st.fontSize);
    const bold = parseInt(st.fontWeight, 10) >= 700;
    const large = size >= 24 || (size >= 18.66 && bold);
    const min = large ? 3 : 4.5;
    if (ratio < min) {
      out.push(`${ratio.toFixed(2)}:1 (need ${min}) ${size}px "${t.slice(0, 34)}" [${el.className.toString().slice(0, 60)}]`);
    }
  });
  return out;
};

let total = 0;
for (const r of routes) {
  await page.goto("http://localhost:3000" + r, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  const res = await page.evaluate(script);
  if (res.length) {
    total += res.length;
    console.log(`\n### ${r}`);
    [...new Set(res)].slice(0, 8).forEach((x) => console.log("  " + x));
  }
}
console.log(total ? `\n${total} low-contrast node(s)` : "\nCONTRAST OK across all routes");
await b.close();
