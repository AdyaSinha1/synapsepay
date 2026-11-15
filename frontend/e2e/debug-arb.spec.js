import { chromium } from "@playwright/test";

const browser = await chromium.launch();
const page = await browser.newPage();
const username = "capt2-" + Date.now().toString(36);
const reg = await (await fetch("http://localhost:8000/api/auth/register", {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username, password: "longenough1" }),
})).json();
const headers = { "Content-Type": "application/json", Authorization: `Bearer ${reg.token}` };
const created = await (await fetch("http://localhost:8000/api/contracts/create", {
  method: "POST", headers,
  body: JSON.stringify({
    title: "arb debug " + Date.now(), bounty_value: 25,
    test_code: "def test_a():\n    assert True\ndef test_b():\n    assert True\ndef test_c():\n    assert True\n",
    run_now: false,
  }),
})).json();
const cid = created.contract.id;
await fetch(`http://localhost:8000/api/contracts/${cid}/accept`, { method: "POST", headers });
await fetch(`http://localhost:8000/api/contracts/${cid}/submit`, {
  method: "POST", headers, body: JSON.stringify({ artifact_type: "code", code: "def solve():\n    return True\n" }),
});
const arb = await fetch(`http://localhost:8000/api/contracts/${cid}/arbitrate`, { method: "POST", headers });
console.log("ARBITRATE STATUS:", arb.status);
console.log("ARBITRATE BODY:", (await arb.text()).slice(0, 400));
await browser.close();
