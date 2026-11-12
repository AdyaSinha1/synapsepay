import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const backendDir = path.join(root, "backend");
const isWin = process.platform === "win32";
const python = process.env.E2E_PYTHON || (isWin ? path.join(backendDir, ".venv", "Scripts", "python.exe") : "python3");

const PORT = 8010;
const BASE = `http://127.0.0.1:${PORT}`;
const DB_URL = `sqlite:///./e2e_persist_${Date.now()}.db`;

function startBackend() {
  const proc = spawn(python, ["-m", "uvicorn", "app.main:app", "--port", String(PORT)], {
    cwd: backendDir,
    env: { ...process.env, DATABASE_URL: DB_URL },
    stdio: "ignore",
  });
  return proc;
}

async function waitHealthy() {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${BASE}/api/health`);
      if (res.ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  throw new Error("backend not healthy");
}

async function stopBackend(proc) {
  if (isWin) {
    const { execSync } = await import("node:child_process");
    try {
      execSync(`taskkill /PID ${proc.pid} /T /F`, { stdio: "ignore" });
    } catch {
      /* gone */
    }
  } else {
    proc.kill();
  }
  await new Promise((r) => setTimeout(r, 800));
}

test("contracts survive a full backend restart", async () => {
  let proc = startBackend();
  await waitHealthy();

  const username = `persist-${Date.now()}`;
  const reg = await fetch(`${BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password: "longenough1" }),
  });
  const { token } = await reg.json();
  const auth = { "Content-Type": "application/json", Authorization: `Bearer ${token}` };

  const created = await fetch(`${BASE}/api/contracts/create`, {
    method: "POST",
    headers: auth,
    body: JSON.stringify({
      title: `persistence probe ${Date.now()}`,
      bounty_value: 10,
      test_code:
        "def test_a():\n    assert True\ndef test_b():\n    assert True\ndef test_c():\n    assert True\n",
      run_now: false,
    }),
  });
  expect(created.status).toBe(200);
  const { contract } = await created.json();

  await stopBackend(proc);
  proc = startBackend();
  await waitHealthy();

  const after = await fetch(`${BASE}/api/contracts/${contract.id}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(after.status).toBe(200);
  const body = await after.json();
  expect(body.contract.title).toContain("persistence probe");
  expect(body.escrow.status).toBe("AUTHORIZED");

  await stopBackend(proc);
});
