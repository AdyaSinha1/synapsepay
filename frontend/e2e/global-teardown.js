async function globalTeardown() {
  const pid = Number(process.env.E2E_BACKEND_PID || 0);
  if (pid && process.platform === "win32") {
    const { execSync } = await import("node:child_process");
    try {
      execSync(`taskkill /PID ${pid} /T /F`, { stdio: "ignore" });
    } catch {
      /* already gone */
    }
  } else if (pid) {
    try {
      process.kill(pid);
    } catch {
      /* already gone */
    }
  }
}

export default globalTeardown;
