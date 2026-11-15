import { expect, test } from "@playwright/test";
import { uid } from "./helpers.js";

const API = "http://localhost:8000";

async function registerViaUi(page, role) {
  const username = `${role}-${uid()}`;
  await page.goto("/login");
  await page.getByRole("button", { name: "Create account" }).first().click();
  await page.getByLabel("Username").fill(username);
  await page.getByLabel(/Password/).fill("longenough-passphrase");
  if (role === "worker") {
    await page.getByRole("button", { name: "worker", exact: true }).click();
  }
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(/dashboard/);
  return { username, password: "longenough-passphrase" };
}

test.describe("access control & console hygiene", () => {
  test("third user opening another user's contract URL sees not-found", async ({ browser, request }) => {
    const hirerReg = await request.post(`${API}/api/auth/register`, {
      data: { username: `e2e-h-${uid()}`, password: "longenough1" },
    });
    const hirerToken = (await hirerReg.json()).token;
    const created = await request.post(`${API}/api/contracts/create`, {
      headers: { Authorization: `Bearer ${hirerToken}` },
      data: {
        title: `access probe ${uid()}`,
        bounty_value: 10,
        test_code: "def test_a():\n    assert True\ndef test_b():\n    assert True\ndef test_c():\n    assert True\n",
        run_now: false,
      },
    });
    expect(created.status()).toBe(200);
    const contractId = (await created.json()).contract.id;

    const context = await browser.newContext();
    const page = await context.newPage();
    await registerViaUi(page, "worker");
    await page.goto(`/contracts/${contractId}`);
    await expect(page.getByText("Contract not found")).toBeVisible({ timeout: 15_000 });
    await context.close();
  });

  test("logged-out session returns to the login screen", async ({ browser }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    await registerViaUi(page, "hirer");
    await page.getByRole("button", { name: "Log out" }).click();
    await expect(page).toHaveURL("/");
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login/);
    await context.close();
  });

  test("Contracts page renders with zero console errors", async ({ browser }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    const consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() !== "error") return;
      // 401 resource noise is expected: anonymous visitors on public pages poll
      // authed endpoints by design. Real app bugs surface as pageerror instead.
      if (msg.text().includes("Failed to load resource")) return;
      consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => consoleErrors.push("PAGEERROR: " + err.message));

    await registerViaUi(page, "hirer");
    await page.goto("/contracts");
    await page.waitForTimeout(2500);
    await expect(page.getByText("New contract").first()).toBeVisible();
    expect(consoleErrors, consoleErrors.join(" | ")).toEqual([]);
    await context.close();
  });

  test("Demo Studio renders with zero console errors (scenarios array hygiene)", async ({ browser }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    const consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() !== "error") return;
      // 401 resource noise is expected: anonymous visitors on public pages poll
      // authed endpoints by design. Real app bugs surface as pageerror instead.
      if (msg.text().includes("Failed to load resource")) return;
      consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => consoleErrors.push("PAGEERROR: " + err.message));

    await page.goto("/studio");
    await page.waitForTimeout(2500);
    await expect(page.getByText("Demo (simulated)").first()).toBeVisible();
    await expect(page.getByText(/Scenario A/).first()).toBeVisible();
    expect(consoleErrors, consoleErrors.join(" | ")).toEqual([]);
    await context.close();
  });
});
