import { chromium } from "@playwright/test";

const browser = await chromium.launch();
const context = await browser.newContext();
const page = await context.newPage();
const errs = [];
page.on("pageerror", (e) => errs.push(e.message));
page.on("console", (m) => { if (m.type() === "error" && !m.text().includes("Failed to load resource")) errs.push(m.text()); });

const username = "boarddbg2-" + Date.now().toString(36);
const reg = await (await fetch("http://localhost:8000/api/auth/register", {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username, password: "longenough1", role: "worker" }),
})).json();
await context.addInitScript(
  ([session]) => localStorage.setItem("synapsepay_session", JSON.stringify(session)),
  [{ token: reg.token, user: reg.user }]
);

await page.goto("http://localhost:5173/board");
await page.waitForTimeout(5000);
const body = await page.locator("body").innerText();
console.log("ERRORS:", errs.slice(0, 3));
console.log("BODY:", body.replace(/\n/g, " | ").slice(0, 400));
await browser.close();
