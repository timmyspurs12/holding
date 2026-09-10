import { chromium } from "playwright";

const BASE = "http://localhost:3000";
const routes = [
  "/",
  "/reporter",
  "/holdings",
  "/holdings/00184",
  "/holdings/00417",
  "/holdings/01042",
  "/cases",
  "/cases/0392",
  "/cases/0417",
  "/cases/1042",
  "/precedent",
  "/domains",
  "/integrations",
  "/developers",
  "/about",
];

const browser = await chromium.launch();
const report = [];

async function audit(route, viewport) {
  const ctx = await browser.newContext({ viewport });
  const page = await ctx.newPage();
  const errs = [];
  page.on("console", (m) => {
    if (m.type() === "error") errs.push(m.text().slice(0, 200));
  });
  page.on("pageerror", (e) => errs.push("pageerror: " + e.message.slice(0, 200)));

  await page.goto(BASE + route, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForTimeout(900);

  const res = await page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const out = { overflow: [], badFonts: new Set(), tinyTap: [], emptyLinks: 0, h1: 0, missingAlt: 0 };

    // horizontal overflow offenders
    document.querySelectorAll("*").forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && (r.right > vw + 1 || r.left < -1)) {
        const style = getComputedStyle(el);
        if (style.overflowX === "visible" && style.position !== "fixed") {
          const parentHidden = (() => {
            let p = el.parentElement;
            while (p) {
              const ps = getComputedStyle(p);
              if (ps.overflowX === "hidden" || ps.overflowX === "auto" || ps.overflowX === "scroll")
                return true;
              p = p.parentElement;
            }
            return false;
          })();
          if (!parentHidden) {
            out.overflow.push(
              `${el.tagName.toLowerCase()}.${(el.className || "").toString().split(" ").slice(0, 2).join(".")} right=${Math.round(r.right)} vw=${vw}`,
            );
          }
        }
      }
    });

    // fonts
    const banned = ["Inter", "Roboto", "Arial", "Poppins", "Montserrat", "Helvetica Neue"];
    document.querySelectorAll("*").forEach((el) => {
      if (!el.textContent?.trim()) return;
      const ff = getComputedStyle(el).fontFamily;
      banned.forEach((b) => {
        if (ff.includes(b)) out.badFonts.add(b + " @ " + el.tagName.toLowerCase());
      });
    });

    // interactive elements too small for touch
    if (window.innerWidth < 768) {
      document.querySelectorAll("a,button,select,input").forEach((el) => {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0 && r.height < 24) {
          out.tinyTap.push(`${el.tagName.toLowerCase()} h=${Math.round(r.height)} "${(el.textContent || "").trim().slice(0, 24)}"`);
        }
      });
    }

    document.querySelectorAll("a").forEach((a) => {
      if (!a.getAttribute("href")) out.emptyLinks++;
    });
    document.querySelectorAll("h1").forEach(() => out.h1++);
    document.querySelectorAll("img").forEach((i) => {
      if (!i.getAttribute("alt")) out.missingAlt++;
    });

    return {
      ...out,
      overflow: out.overflow.slice(0, 6),
      badFonts: [...out.badFonts],
      tinyTap: out.tinyTap.slice(0, 6),
      docScrollWidth: document.documentElement.scrollWidth,
      vw,
      bodyH: document.body.scrollHeight,
    };
  });

  report.push({ route, viewport: viewport.width, ...res, errs: errs.slice(0, 4) });
  await ctx.close();
}

for (const r of routes) {
  await audit(r, { width: 1440, height: 900 });
  await audit(r, { width: 390, height: 844 });
}

let issues = 0;
for (const r of report) {
  const problems = [];
  if (r.docScrollWidth > r.vw + 1) problems.push(`H-SCROLL doc=${r.docScrollWidth} vw=${r.vw}`);
  if (r.overflow.length) problems.push(`OVERFLOW: ${r.overflow.join(" | ")}`);
  if (r.badFonts.length) problems.push(`BANNED FONT: ${r.badFonts.join(", ")}`);
  if (r.tinyTap.length) problems.push(`TINY TAP: ${r.tinyTap.join(" | ")}`);
  if (r.emptyLinks) problems.push(`EMPTY HREF x${r.emptyLinks}`);
  if (r.h1 !== 1) problems.push(`H1 COUNT = ${r.h1}`);
  if (r.missingAlt) problems.push(`IMG MISSING ALT x${r.missingAlt}`);
  if (r.errs.length) problems.push(`CONSOLE: ${r.errs.join(" | ")}`);

  if (problems.length) {
    issues += problems.length;
    console.log(`\n### ${r.route} @ ${r.viewport}`);
    problems.forEach((p) => console.log("   - " + p));
  }
}
console.log(`\n${issues ? issues + " issue(s) found" : "CLEAN — no layout, font, a11y or console issues"}`);
await browser.close();
