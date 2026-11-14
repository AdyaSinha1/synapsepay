import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import confetti from "canvas-confetti";
import {
  acceptContract as acceptApi,
  arbitrate as arbitrateApi,
  API_BASE,
  createContract,
  fundComplete,
  fundStart,
  getContracts,
  getHealth,
  getMetrics,
  getRecentEvents,
  getScenarios,
  getUser,
  loginAccount,
  logoutAccount,
  registerAccount,
  runDemo,
  submitDeliverable,
  zipContracts,
} from "./api.js";
import { clearSession, getSession, getToken } from "./auth.js";

const AppContext = createContext(null);

const MILESTONES = {
  contract_formulated: 1,
  paypal_authorized: 2,
  worker_delivered: 3,
  arbiter_decision: 4,
  paypal_settlement: 5,
};

function mergeEvents(streamed, finalEvents) {
  const seen = new Set(streamed.map((e) => `${e.ts}|${e.stage}|${e.message}`));
  return [...streamed, ...(finalEvents || []).filter((e) => !seen.has(`${e.ts}|${e.stage}|${e.message}`))];
}

export function AppProvider({ children }) {
  const [health, setHealth] = useState(null);
  const [everFailed, setEverFailed] = useState(false);
  const [scenarios, setScenarios] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [contractsRaw, setContractsRaw] = useState(null);
  const [lastRun, setLastRun] = useState(null);
  const [lastEscrow, setLastEscrow] = useState(null);
  const [liveEvents, setLiveEvents] = useState([]);
  const [runStage, setRunStage] = useState(0);
  const [running, setRunning] = useState(false);
  const [activeScenario, setActiveScenario] = useState(null);
  const [toast, setToast] = useState(null);
  const [errorPanel, setErrorPanel] = useState(null);
  const [user, setUser] = useState(() => getUser());
  const [bellEvents, setBellEvents] = useState([]);
  const toastTimer = useRef(null);

  const showToast = useCallback((msg, tone = "volt") => {
    clearTimeout(toastTimer.current);
    setToast({ msg, tone });
    toastTimer.current = setTimeout(() => setToast(null), 4500);
  }, []);

  const showError = useCallback((e) => {
    setToast(null);
    setErrorPanel(String((e && e.message) || e || "Unknown error"));
  }, []);

  const celebrate = useCallback(() => {
    confetti({
      particleCount: 160,
      spread: 75,
      origin: { y: 0.6 },
      colors: ["#D9F45B", "#8B7BE8", "#262038"],
    });
  }, []);

  const refreshData = useCallback(async () => {
    try {
      const [h, m, c] = await Promise.all([getHealth(), getMetrics(), getContracts()]);
      setHealth(h);
      setMetrics(m);
      setContractsRaw(c);
      setEverFailed(false);
    } catch {
      setHealth(null);
      setEverFailed(true);
    }
  }, []);

  useEffect(() => {
    getScenarios().then(setScenarios).catch(() => {});
    refreshData();
    const id = setInterval(refreshData, 12000);
    return () => clearInterval(id);
  }, [refreshData]);

  useEffect(() => {
    let closed = false;
    let ws;
    const connect = () => {
      ws = new WebSocket(`${API_BASE.replace(/^http/, "ws")}/ws/events`);
      ws.addEventListener("open", () => {
        const token = getToken();
        if (token) ws.send(JSON.stringify({ token }));
      });
      ws.onmessage = (e) => {
        try {
          const evt = JSON.parse(e.data);
          setLiveEvents((prev) => [...prev, evt]);
          const milestone = MILESTONES[evt.stage];
          if (milestone) setRunStage((s) => Math.max(s, milestone));
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = () => {
        if (!closed) setTimeout(connect, 3000);
      };
    };
    connect();
    return () => {
      closed = true;
      if (ws) ws.close();
    };
  }, []);

  useEffect(() => {
    const load = () => getRecentEvents(25).then((d) => setBellEvents(d.events || [])).catch(() => {});
    load();
    const id = setInterval(load, 20000);
    return () => clearInterval(id);
  }, []);

  const runCycle = useCallback(
    async (payload, { scenarioId = null } = {}) => {
      setRunning(true);
      setLiveEvents([]);
      setRunStage(0);
      setActiveScenario(scenarioId);
      try {
        const data = await runDemo(payload);
        setLastRun(data);
        setLiveEvents((prev) => mergeEvents(prev, data.events));
        setRunStage(5);
        await refreshData();
        if (data.evaluation?.decision === "CAPTURE") {
          celebrate();
          showToast(`Captured ${data.receipt?.transaction_id} — worker paid`, "volt");
        } else {
          showToast(`Voided — hirer refunded (${data.receipt?.transaction_id})`, "coral");
        }
        return data;
      } finally {
        setRunning(false);
        setActiveScenario(null);
      }
    },
    [celebrate, refreshData, showToast]
  );

  const runScenario = useCallback((scenarioId) => runCycle({ scenario_id: scenarioId }, { scenarioId }), [runCycle]);

  const createAndRun = useCallback(
    async (payload) => {
      if (payload.scenario_id) {
        await runScenario(payload.scenario_id);
        return null;
      }
      const created = await createContract(payload);
      setLastEscrow(created.escrow);
      showToast("Escrow authorized — funds reserved (not deposited)", "lilac");
      await refreshData();
      if (payload.run_now !== false) {
        try {
          const result = await runCycle({ contract_id: created.contract.id });
          return result;
        } catch (e) {
          showError(e);
          return created;
        }
      }
      return created;
    },
    [refreshData, runCycle, runScenario, showError, showToast]
  );

  const runArbitration = useCallback(
    async (contractId, code) => {
      if (code !== undefined) {
        await submitDeliverable(contractId, {
          artifact_type: "code",
          code,
          notes: "Submitted via SynapsePay UI",
        });
      }
      const res = await arbitrateApi(contractId);
      await refreshData();
      if (res.evaluation?.decision === "CAPTURE") {
        celebrate();
        showToast(`Captured ${res.receipt?.transaction_id} — worker paid`, "volt");
      } else {
        showToast(`Voided — hirer refunded (${res.receipt?.transaction_id})`, "coral");
      }
      return res;
    },
    [celebrate, refreshData, showToast]
  );

  const safeRun = useCallback((fn) => fn().catch(showError), [showError]);

  const acceptAction = useCallback(
    async (contractId, workerName) => {
      const res = await acceptApi(contractId, workerName || "");
      await refreshData();
      showToast(`Contract accepted by ${res.worker}`, "lilac");
      return res;
    },
    [refreshData, showToast]
  );

  const fundSimulated = useCallback(
    async (contractId) => {
      const start = await fundStart(contractId);
      const done = await fundComplete(contractId, start.order_id);
      await refreshData();
      showToast("Escrow funded (simulated) — funds reserved, not deposited", "volt");
      return done;
    },
    [refreshData, showToast]
  );

  const loginUser = useCallback(async (username, password) => {
    const u = await loginAccount(username, password);
    setUser(u);
    showToast(`Welcome back, ${u.display_name}`, "volt");
    return u;
  }, [showToast]);

  const registerUserFn = useCallback(async (username, password, role, displayName) => {
    const u = await registerAccount(username, password, role, displayName);
    setUser(u);
    showToast(`Account created — welcome, ${u.display_name}`, "volt");
    return u;
  }, [showToast]);

  const logoutUser = useCallback(async () => {
    await logoutAccount();
    clearSession();
    setUser(null);
    showToast("Logged out", "slate");
  }, [showToast]);

  const contracts = zipContracts(contractsRaw);

  const value = {
    health, everFailed, scenarios, metrics, contractsRaw, contracts,
    lastRun, lastEscrow, liveEvents, runStage, running, activeScenario,
    user, bellEvents,
    toast, errorPanel, showError, showToast,
    refreshData, runScenario, createAndRun, runArbitration, acceptAction, fundSimulated,
    loginUser, registerUserFn, logoutUser,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside AppProvider");
  return ctx;
}
