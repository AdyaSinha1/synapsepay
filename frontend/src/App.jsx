import { useCallback, useEffect, useRef, useState } from "react";
import confetti from "canvas-confetti";
import { CheckCircle2, XCircle } from "lucide-react";
import Sidebar from "./components/Sidebar.jsx";
import Topbar from "./components/Topbar.jsx";
import Overview from "./pages/Overview.jsx";
import Contracts from "./pages/Contracts.jsx";
import DemoStudio from "./pages/DemoStudio.jsx";
import Agents from "./pages/Agents.jsx";
import Arbiter from "./pages/Arbiter.jsx";
import Payments from "./pages/Payments.jsx";
import {
  API_BASE,
  arbitrate as arbitrateApi,
  createContract,
  getContracts,
  getHealth,
  getMetrics,
  getScenarios,
  runDemo,
  submitDeliverable,
} from "./api.js";

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

export default function App() {
  const [page, setPage] = useState("overview");
  const [health, setHealth] = useState(null);
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
  const toastTimer = useRef(null);

  const showToast = useCallback((msg, tone = "volt") => {
    clearTimeout(toastTimer.current);
    setToast({ msg, tone });
    toastTimer.current = setTimeout(() => setToast(null), 4500);
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
    } catch {
      setHealth(null);
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
        return;
      }
      const created = await createContract(payload);
      setLastEscrow(created.escrow);
      showToast("Escrow authorized — funds locked", "lilac");
      await refreshData();
      if (payload.run_now !== false) {
        try {
          await runCycle({ contract_id: created.contract.id });
        } catch (e) {
          showToast(String(e.message || e), "coral");
        }
      }
    },
    [refreshData, runCycle, runScenario, showToast]
  );

  const runArbitration = useCallback(
    async (contractId, code) => {
      await submitDeliverable(contractId, {
        artifact_type: "code",
        code,
        notes: "Submitted from the AI Arbiter page",
      });
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

  const safeRun = useCallback(
    (fn) => {
      fn().catch((e) => showToast(String(e.message || e), "coral"));
    },
    [showToast]
  );

  const contracts = [];
  if (contractsRaw && Array.isArray(contractsRaw.contracts)) {
    const escrows = contractsRaw.escrows || [];
    contractsRaw.contracts
      .map((c) => ({ ...c, escrow: escrows.find((e) => e.contract_id === c.id) || null }))
      .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""))
      .forEach((c) => contracts.push(c));
  }

  const pages = {
    overview: (
      <Overview
        metrics={metrics}
        contractsRaw={contractsRaw}
        lastRun={lastRun}
        running={running}
        onRunDemo={(sid) => safeRun(() => runScenario(sid))}
        onNavigate={setPage}
      />
    ),
    contracts: (
      <Contracts
        scenarios={scenarios}
        contracts={contracts}
        running={running}
        onCreateAndRun={(p) => safeRun(() => createAndRun(p))}
        onRunCycle={(cid) => safeRun(() => runCycle({ contract_id: cid }))}
        lastEscrow={lastEscrow}
      />
    ),
    studio: (
      <DemoStudio
        scenarios={scenarios}
        running={running}
        liveEvents={liveEvents}
        runStage={runStage}
        lastRun={lastRun}
        activeScenario={activeScenario}
        onRunScenario={(sid) => safeRun(() => runScenario(sid))}
      />
    ),
    agents: <Agents metrics={metrics} lastRun={lastRun} liveEvents={liveEvents} running={running} />,
    arbiter: (
      <Arbiter
        contracts={contracts}
        running={running}
        onArbitrateRun={runArbitration}
        onNavigate={setPage}
      />
    ),
    payments: (
      <Payments
        metrics={metrics}
        contractsRaw={contractsRaw}
        running={running}
        onRunDemo={(sid) => safeRun(() => runScenario(sid))}
        onNavigate={setPage}
      />
    ),
  };

  return (
    <div className="flex min-h-screen">
      <Sidebar page={page} onNavigate={setPage} health={health} />
      <div className="min-w-0 flex-1">
        <Topbar page={page} health={health} onNavigate={setPage} />
        <main className="mx-auto max-w-6xl px-5 py-8 sm:px-8">{pages[page]}</main>
      </div>

      {toast && (
        <div
          className={`fade-up fixed bottom-6 right-6 z-50 flex items-center gap-2.5 rounded-2xl border px-4 py-3 text-sm font-semibold shadow-card ${
            toast.tone === "coral"
              ? "border-coral/30 bg-coral-100 text-coral-ink"
              : toast.tone === "lilac"
                ? "border-lilac/30 bg-lilac-100 text-lilac-ink"
                : "border-volt-deep/40 bg-volt-soft text-volt-ink"
          }`}
        >
          {toast.tone === "coral" ? <XCircle className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
          {toast.msg}
        </div>
      )}
    </div>
  );
}
