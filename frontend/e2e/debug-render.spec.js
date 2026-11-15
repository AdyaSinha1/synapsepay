import { chromium } from "@playwright/test";

const browser = await chromium.launch();
const out = [];

// anon /studio
const p1 = await browser.newPage();
const errs1 = [];
p1.on("pageerror", (e) => errs1.push(e.message));
await p1.goto("http://localhost:5173/studio");
await p1.waitForTimeout(4000);
out.push("STUDIO(anon): " + (await p1.locator("body").innerText()).replace(/\n/g, " | ").slice(0, 250));
out.push("STUDIO errors: " + errs1.join(" ; ").slice(0, 200));

// authed /contracts
const reg = await (await fetch("http://localhost:8000/api/auth/register", {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username: "dbg9-" + Date.now(), password: "longenough1" }),
})).json();
const p2 = await browser.newPage();
const errs2 = [];
p2.on("pageerror", (e) => errs2.push(e.message));
await p2.addInitScript(
  ([session]) => localStorage.setItem("synapsepay_session", JSON.stringify(session)),
  [{ token: reg.token, user: reg.user }]
);
await p2.goto("http://localhost:5173/contracts");
await p2.waitForTimeout(4000);
out.push("CONTRACTS(auth): " + (await p2.locator("body").innerText()).replace(/\n/g, " | ").slice(0, 350));
out.push("CONTRACTS errors: " + errs2.join(" ; ").slice(0, 200));

await browser.close();
console.log(out.join("\n===\n"));
