import { Check, Loader2, Play } from "lucide-react";
import EventFeed from "../components/EventFeed.jsx";
import Pipeline from "../components/Pipeline.jsx";
import { Chip, PageIntro } from "../components/ui.jsx";
import { fmtUSD } from "../api.js";

function outcomeInfo(expected, amount) {
  if (expected === "CAPTURE") return { tone: "volt", label: `Will capture ${fmtUSD(amount)}` };
  if (expected === "PARTIAL") return { tone: "sun", label: "Will partially capture" };
  return { tone: "coral", label: `Will void ${fmtUSD(amount)}` };
}

export default function DemoStudio({
  scenarios,
  running,
  liveEvents,
  runStage,
  lastRun,
  onRunScenario,
  activeScenario,
}) {
  const decision = lastRun?.evaluation?.decision || null;
  const captured = decision === "CAPTURE";

  return (
    <div className="space-y-6">
      <PageIntro
        title="Demo Studio"
        sub="Three pre-built contracts with known outcomes. Run one and watch escrow lock, work execute, and the arbiter decide — live."
      />

      <div className="grid gap-4 lg:grid-cols-3">
        {scenarios.map((s) => {
          const outcome = outcomeInfo(s.expected, s.amount);
          const isActive = running && activeScenario === s.id;
          return (
            <div key={s.id} className={`card flex flex-col p-5 ${isActive ? "border-lilac/60 shadow-[0_0_0_3px_rgba(139,123,232,0.15)]" : ""}`}>
              <div className="mb-3 flex items-center justify-between gap-2">
                <Chip tone={outcome.tone}>{outcome.label}</Chip>
                <span className="font-mono text-[10px] uppercase tracking-wider text-mute/60">Scenario {s.id}</span>
              </div>
              <h3 className="font-display text-base font-bold text-ink">{s.subtitle}</h3>
              <p className="mt-1.5 flex-1 text-xs leading-relaxed text-mute">{s.description}</p>
              <ul className="mt-3 space-y-1.5">
                {s.acceptance_criteria.slice(0, 3).map((c) => (
                  <li key={c} className="flex items-start gap-1.5 text-[11px] leading-snug text-mute">
                    <Check className="mt-0.5 h-3 w-3 shrink-0 text-volt-deep" /> {c}
                  </li>
                ))}
                {s.acceptance_criteria.length > 3 && (
                  <li className="text-[11px] text-mute/70">+ {s.acceptance_criteria.length - 3} more criteria</li>
                )}
              </ul>
              <button className="btn-plum mt-4 w-full" onClick={() => onRunScenario(s.id)} disabled={running}>
                {isActive ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                {isActive ? "Running scenario…" : `Run scenario ${s.id}`}
              </button>
            </div>
          );
        })}
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="card p-6 lg:col-span-2">
          <h2 className="mb-4 font-display text-base font-bold text-ink">Live escrow pipeline</h2>
          <Pipeline stage={runStage} running={running} decision={decision} />
          {lastRun && !running && (
            <div className={`fade-up mt-4 rounded-xl p-4 ${captured ? "bg-volt-soft" : "bg-coral-100"}`}>
              <p className={`text-sm font-bold ${captured ? "text-volt-ink" : "text-coral-ink"}`}>
                {captured ? "Captured — worker paid" : "Voided — hirer refunded"}
              </p>
              <p className="mt-1 font-mono text-[11px] text-mute">
                {lastRun.receipt?.transaction_id} · {(lastRun.total_ms / 1000).toFixed(1)}s cycle
              </p>
            </div>
          )}
        </div>

        <div className="lg:col-span-3">
          <div className="card p-6">
            <h2 className="mb-4 font-display text-base font-bold text-ink">Arbiter telemetry</h2>
            <EventFeed events={liveEvents} height="h-[420px]" placeholder="Pick a scenario above — every agent step streams here in real time." />
          </div>
        </div>
      </div>
    </div>
  );
}
