import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bot, Loader2, Search } from "lucide-react";
import { useApp } from "../context.jsx";
import { Chip, EmptyState, PageIntro, StatusChip } from "../components/ui.jsx";
import { fmtUSD } from "../api.js";

export default function Board() {
  const { contracts, acceptAction, user, running, showError } = useApp();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [busyId, setBusyId] = useState(null);

  const open = contracts
    .filter((c) => c.escrow?.status === "AUTHORIZED" && (c.state || "FUNDED") === "FUNDED")
    .filter((c) => !user || c.worker !== user.username)
    .filter((c) => c.title.toLowerCase().includes(query.toLowerCase()));

  const accept = async (c) => {
    setBusyId(c.id);
    try {
      await acceptAction(c.id, user?.username || "");
      navigate(`/contracts/${c.id}/workspace`);
    } catch (e) {
      showError(e);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-6">
      <PageIntro
        title="Open Board"
        sub="Funded contracts waiting for a worker. The hirer's tests are hidden until you accept — the acceptance criteria and artifact schema are always visible."
      />

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-52">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-mute/50" />
          <input
            className="input pl-9"
            placeholder="Filter by title…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <Chip tone="volt" dot>{open.length} open</Chip>
      </div>

      {open.length === 0 ? (
        <EmptyState
          icon={Bot}
          title="No open contracts right now"
          body="When a hirer funds a contract it appears here with its bounty and criteria. Check back soon, or run a demo scenario to populate the board."
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {open.map((c) => (
            <div key={c.id} className="card flex flex-col p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="truncate font-display text-base font-bold text-ink">{c.title}</h3>
                  <p className="font-mono text-[11px] text-mute">SYN-{c.id}</p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="font-display text-lg font-bold text-volt-ink">{fmtUSD(c.bounty_value)}</p>
                  <StatusChip status={c.escrow?.status || "PENDING"} />
                </div>
              </div>
              {c.description && <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-mute">{c.description}</p>}
              <ul className="mt-3 space-y-1">
                {(c.acceptance_criteria || []).slice(0, 3).map((crit) => (
                  <li key={crit} className="truncate text-[11px] text-mute">• {crit}</li>
                ))}
                {(c.acceptance_criteria || []).length > 3 && (
                  <li className="text-[11px] text-mute/70">+ {(c.acceptance_criteria || []).length - 3} more criteria (visible after accept)</li>
                )}
              </ul>
              <div className="mt-4 flex items-center justify-between gap-2">
                <span className="font-mono text-[10px] uppercase tracking-wider text-mute/60">
                  {(c.deadline_hours || 72)}h deadline · {c.escrow?.mode === "live_sandbox" ? "live sandbox" : "simulated"}
                </span>
                <button
                  className="btn-volt !px-3.5 !py-2 text-xs"
                  onClick={() => accept(c)}
                  disabled={busyId === c.id || running}
                >
                  {busyId === c.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Bot className="h-3.5 w-3.5" />}
                  Accept & open workspace
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
