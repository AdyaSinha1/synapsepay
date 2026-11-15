import { chromium } from "@playwright/test";

const browser = await chromium.launch();
const context = await browser.newContext();
const page = await context.newPage();

const username = "captdbg-" + Date.now().toString(36);
const reg = await (await fetch("http://localhost:8000/api/auth/register", {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username, password: "longenough1" }),
})).json();
await context.addInitScript(
  ([session]) => localStorage.setItem("synapsepay_session", JSON.stringify(session)),
  [{ token: reg.token, user: reg.user }]
);

// create + fund + accept + submit + arbitrate via API, then inspect the UI page
const headers = { "Content-Type": "application/json", Authorization: `Bearer ${reg.token}` };
const created = await (await fetch("http://localhost:8000/api/contracts/create", {
  method: "POST", headers,
  body: JSON.stringify({
    title: "captured debug " + Date.now(), bounty_value: 25,
    test_code: "def test_a():\n    assert True\ndef test_b():\n    assert True\ndef test_c():\n    assert True\n",
    run_now: false,
  }),
})).json();
const cid = created.contract.id;
await fetch(`http://localhost:8000/api/contracts/${cid}/accept`, { method: "POST", headers });
await fetch(`http://localhost:8000/api/contracts/${cid}/submit`, {
  method: "POST", headers,
  body: JSON.stringify({ artifact_type: "code", code: "def solve():\n    return True\n" }),
});
const arb = await (await fetch(`http://localhost:8000/api/contracts/${cid}/arbitrate`, { method: "POST", headers })).json();
console.log("API ARBITRATE:", arb.escrow?.status, "| receipt:", arb.receipt?.settlement_type);

await page.goto(`http://localhost:5173/contracts/${cid}`);
await page.waitForTimeout(4000);
const body = await page.locator("body").innerText();
console.log("HAS Captured:", body.includes("Captured"));
console.log("HAS Receipt:", body.includes("Receipt"));
console.log("BODY:", body.replace(/\n/g, " | ").slice(0, 500));
await browser.close();
