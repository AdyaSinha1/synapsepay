import { Asterisk, Bot, FileSignature } from "lucide-react";
import EventFeed from "../components/EventFeed.jsx";
import FlowSteps from "../components/FlowSteps.jsx";
import { Chip, PageIntro, SectionHeader, StatCard } from "../components/ui.jsx";
import { fmtPct } from "../api.js";

export default function Agents({ metrics, lastRun, liveEvents, running }) {
  const m = metrics || { cycles: 0, avg_arbiter_ms: 0, success_rate: 0 };
  const hasData = m.cycles > 0;

  const agents = [
    {
      icon: FileSignature,
      name: "Orchestrator agent A",
      role: "The Hirer",
      tint: "bg-plum-100 text-plum-800",
      desc: "Writes the TaskSpec, sets the bounty and acceptance criteria, then locks real fiat in PayPal escrow before any work begins.",
      stat: hasData ? `${String(m.cycles).padStart(2, "0")} contracts processed` : "Awaiting first contract",
      chip: <Chip tone="plum">Hirer</Chip>,
    },
    {
      icon: Bot,
      name: "Worker agent B",
      role: "The Builder",
      tint: "bg-plum-100 text-plum-800",
      desc: "Ingests the contract, executes the workload, and submits the deliverable artifact. Payment depends entirely on the arbiter's verdict.",
      stat: hasData ? `${String(m.cycles).padStart(2, "0")} deliverables submitted` : "No deliverables yet",
      chip: <Chip tone="plum">Worker</Chip>,
    },
    {
      icon: Asterisk,
      name: "Neural Arbiter",
      role: "The AI Judge",
      tint: "bg-lilac-200 text-lilac-ink",
      desc: "Impartial referee. Runs unit tests in a sandbox, checks schema policy, and asks the LLM to review quality — then applies the 85% threshold rule.",
      stat: hasData ? `Avg verdict in ${(m.avg_arbiter_ms / 1000).toFixed(1)}s` : "Ready to evaluate",
      chip: <Chip tone="lilac">Arbiter</Chip>,
    },
  ];

  return (
    <div className="space-y-6">
      <PageIntro
        title="AI Agents"
        sub="Three autonomous parties with fixed roles in every escrow cycle. The operator runs the arbiter and PayPal holds the funds — this is trust-minimized automation, not a permissionless protocol."
      />

      <div className="grid gap-4 lg:grid-cols-3">
        {agents.map((a) => (
          <div key={a.name} className="card p-6">
            <div className="flex items-start justify-between">
              <div className={`flex h-12 w-12 items-center justify-center rounded-2xl ${a.tint}`}>
                <a.icon className="h-5 w-5" />
              </div>
              {a.chip}
            </div>
            <h3 className="mt-4 font-display text-base font-bold text-ink">{a.name}</h3>
            <p className="text-xs font-semibold text-lilac-ink">{a.role}</p>
            <p className="mt-2 text-xs leading-relaxed text-mute">{a.desc}</p>
            <p className="mt-4 rounded-lg bg-[#FBFAF5] px-3 py-2 font-mono text-[11px] text-mute">{a.stat}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="card p-6 lg:col-span-2">
          <SectionHeader title="How they collaborate" sub="The same five steps, every cycle." />
          <FlowSteps compact />
          <div className="mt-6 grid grid-cols-2 gap-3">
            <StatCard
              label="Success rate"
              value={hasData ? fmtPct(m.success_rate) : "—"}
              sub="Captures over all cycles"
            />
            <StatCard
              label="Cycles run"
              value={hasData ? String(m.cycles).padStart(2, "0") : "00"}
              sub="This server session"
            />
          </div>
        </div>
        <div className="lg:col-span-3">
          <div className="card p-6">
            <SectionHeader
              title="Agent activity feed"
              sub="Live event stream from the most recent escrow cycle."
              badge={running ? <Chip tone="lilac" dot>Live</Chip> : undefined}
            />
            <EventFeed
              events={liveEvents}
              height="h-80"
              placeholder="Run a scenario and the agents' conversation appears here."
            />
          </div>
        </div>
      </div>
    </div>
  );
}
