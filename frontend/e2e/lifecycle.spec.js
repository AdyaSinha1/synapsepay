import { expect, test } from "@playwright/test";
import { uid } from "./helpers.js";

const PASSING_SLUGIFY = `def slugify(text):
    """Convert a title into a URL slug."""
    return '-'.join(text.lower().strip().split())
`;

const FAILING_SLUGIFY = `def slugify(text):
    """Almost right, but forgets lowercasing."""
    return '-'.join(text.strip().split())
`;

async function register(page, role) {
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

async function createFundedContract(page, title) {
  await page.goto("/contracts/new");
  await page.getByPlaceholder("Build a URL slug helper").fill(title);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: /Save draft & continue to funding/ }).click();
  await page.getByRole("button", { name: /Fund \(simulated\)/ }).click();
  await expect(page).toHaveURL(/\/contracts\/[a-f0-9]+$/, { timeout: 30_000 });
  await expect(page.getByText("Funds are RESERVED")).toBeVisible();
  return page.url().split("/").pop();
}

test.describe.serial("full contract lifecycle", () => {
  let contractId;
  const title = `E2E slug helper ${uid()}`;

  test("hirer registers and funds a contract through the wizard", async ({ page }) => {
    await register(page, "hirer");
    contractId = await createFundedContract(page, title);
    await expect(page.getByText("Escrow active")).toBeVisible();
  });

  test("worker claims it from the board and submits passing code", async ({ browser }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    await register(page, "worker");

    await page.goto("/board");
    const card = page.locator(".card", { hasText: title }).first();
    await expect(card).toBeVisible();
    await card.getByRole("button", { name: /Accept & open workspace/ }).click();
    await expect(page).toHaveURL(/workspace$/);

    await page.locator("textarea").first().fill(PASSING_SLUGIFY);
    await page.getByRole("button", { name: /Submit & run arbitration/ }).click();
    await expect(page.getByText(/Captured —/)).toBeVisible({ timeout: 30_000 });
    await context.close();
  });

  test("both parties see the settled receipt on the contract page", async ({ page }) => {
    await page.goto(`/contracts/${contractId}`);
    await expect(page.getByText("Captured").first()).toBeVisible();
    await expect(page.getByText("Receipt")).toBeVisible();
    await expect(page.getByText(/The capture completed the charge/)).toBeVisible();
  });

  test("a third account can view it, but a bogus id renders not-found", async ({ browser }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    await register(page, "hirer");
    await page.goto(`/contracts/${contractId}`);
    await expect(page.getByText("Captured").first()).toBeVisible();

    await page.goto("/contracts/doesnotexist99");
    await expect(page.getByText("Contract not found")).toBeVisible();
    await context.close();
  });

  test("a failing submission opens remediation, then a resubmission settles", async ({ browser }) => {
    const hirerContext = await browser.newContext();
    const hirerPage = await hirerContext.newPage();
    await register(hirerPage, "hirer");
    const remediationTitle = `E2E remediation ${uid()}`;
    const remediationId = await createFundedContract(hirerPage, remediationTitle);
    await hirerContext.close();

    const workerContext = await browser.newContext();
    const workerPage = await workerContext.newPage();
    await register(workerPage, "worker");
    await workerPage.goto("/board");
    const card = workerPage.locator(".card", { hasText: remediationTitle }).first();
    await card.getByRole("button", { name: /Accept & open workspace/ }).click();
    await expect(workerPage).toHaveURL(/workspace$/);

    await workerPage.locator("textarea").first().fill(FAILING_SLUGIFY);
    await workerPage.getByRole("button", { name: /Submit & run arbitration/ }).click();
    await expect(workerPage.getByText(/Remediation round open/)).toBeVisible({ timeout: 30_000 });

    await workerPage.locator("textarea").first().fill(PASSING_SLUGIFY);
    await workerPage.getByRole("button", { name: /Resubmit & re-arbitrate/ }).click();
    await expect(workerPage.getByText(/Captured —/)).toBeVisible({ timeout: 30_000 });
    await workerContext.close();
  });

  test("logout returns the visitor to the landing page", async ({ page }) => {
    await register(page, "hirer");
    await page.getByRole("button", { name: "Log out" }).click();
    await expect(page.getByText("They need escrow.")).toBeVisible();
  });
});
