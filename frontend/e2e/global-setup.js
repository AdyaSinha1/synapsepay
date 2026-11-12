import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const backendDir = path.join(root, "backend");

const isWin = process.platform === "win32";
const python = process.env.E2E_PYTHON || (isWin ? path.join(backendDir, ".venv", "Scripts", "python.exe") : "python3");

let backendProc;

export default async function globalSetup() {
  backendProc = spawn(
    python,
    ["-m", "uvicorn", "app.main:app", "--port", "8000"],
    {
      cwd: backendDir,
      env: {
        ...process.env,
        DATABASE_URL: "sqlite:///./e2e_test.db",
        REQUIRE_AUTH: "false",
        DOCS_ENABLED: "false",
      },
      stdio: "ignore",
    }
  );
  process.env.E2E_BACKEND_PID = String(backendProc.pid);

  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    try {
      const res = await fetch("http://127.0.0.1:8000/api/health");
      if (res.ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("backend did not become healthy within 60s");
}

export { backendProc };
