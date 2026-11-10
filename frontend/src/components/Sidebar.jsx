import { ArrowUpRight, Asterisk, Diamond, Home, PlayCircle, ScrollText } from "lucide-react";

export const NAV_ITEMS = [
  { id: "overview", label: "Overview", icon: Home },
  { id: "contracts", label: "Contracts", icon: ScrollText },
  { id: "studio", label: "Demo Studio", icon: PlayCircle },
  { id: "agents", label: "AI Agents", icon: Diamond },
  { id: "arbiter", label: "AI Arbiter", icon: Asterisk },
  { id: "payments", label: "Payments", icon: ArrowUpRight },
];

export default function Sidebar({ page, onNavigate, health }) {
  const online = Boolean(health);
  const paypalLine = !online
    ? "API OFFLINE"
    : health.paypal_mode === "live_sandbox"
      ? "PAYPAL SANDBOX · LIVE KEYS"
      : "PAYPAL SANDBOX · SIMULATED";
  const geminiLine = !online ? "START WITH RUN.BAT" : health.gemini_mode === "live" ? "GEMINI LIVE" : "GEMINI READY";

  return (
    <aside className="hidden w-64 shrink-0 flex-col justify-between bg-plum-900 md:sticky md:top-0 md:flex md:h-screen">
      <div>
        <div className="flex items-center gap-3 px-5 pb-6 pt-6">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-volt font-display text-xl font-extrabold text-plum-900 shadow-volt">
            S
          </div>
          <div>
            <p className="font-display text-lg font-bold leading-tight text-white">
              synapse<span className="text-volt">pay</span>
            </p>
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-white/40">
              Agent escrow protocol
            </p>
          </div>
        </div>

        <p className="px-6 pb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-white/30">Workspace</p>
        <nav className="space-y-1 px-3">
          {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
            const active = page === id;
            return (
              <button
                key={id}
                onClick={() => onNavigate(id)}
                className={`flex w-full items-center gap-3 rounded-xl px-4 py-2.5 text-sm font-medium transition ${
                  active ? "bg-plum-800 text-white" : "text-white/55 hover:bg-plum-800/50 hover:text-white/90"
                }`}
              >
                <Icon className={`h-4 w-4 ${active ? "text-volt" : "text-white/40"}`} />
                {label}
              </button>
            );
          })}
        </nav>
      </div>

      <div className="px-4 pb-5">
        <div className="rounded-2xl bg-plum-800 p-4">
          <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-volt">
            <span className={`h-2 w-2 rounded-full ${online ? "animate-pulse bg-volt" : "bg-coral"}`} />
            {online ? "System operational" : "Backend offline"}
          </p>
          <p className="mt-2 text-[11px] leading-relaxed text-white/50">
            {online
              ? "All services connected in demo mode. Transactions are simulated."
              : "Start the API with run.bat, this panel updates automatically."}
          </p>
          <p className="mt-3 font-mono text-[9px] uppercase tracking-wider text-white/30">
            {paypalLine} · {geminiLine}
          </p>
        </div>
        <p className="px-2 pt-4 font-mono text-[10px] uppercase tracking-wider text-white/25">
          SynapsePay protocol · v1.0.0
        </p>
      </div>
    </aside>
  );
}
