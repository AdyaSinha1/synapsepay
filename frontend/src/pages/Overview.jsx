import { ArrowRight, Asterisk, Clock, Eye, Layers, TrendingUp, Wallet } from "lucide-react";
import EvaluationCard from "../components/EvaluationCard.jsx";
import FlowSteps from "../components/FlowSteps.jsx";
import TransactionTable from "../components/TransactionTable.jsx";
import { Chip, PageIntro, SampleTag, StatCard } from "../components/ui.jsx";
import { fmtPct, fmtUSD, zipContracts } from "../api.js";

export default function Overview({ metrics, contractsRaw, lastRun, running, onRunDemo, onNavigate }) {
  const rows = zipContracts(contractsRaw).slice(0, 4);
  const hasMetrics = Boolean(metrics && metrics.cycles > 0);

  return (
    <div className="space-y-6">
      <PageIntro
        title={
          <span className="flex items-center gap-2">
            Good to see you. <Asterisk className="h-6 w-6 text-lilac" />
          </span>
        }
        sub="Here's what's happening across your agent economy."
        action={
          <button className="btn-volt" onClick={() => onNavigate("contracts")} disabled={running}>
            + New contract
          </button>
        }
      />

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard
          icon={Eye}
          label="Total authorized"
          value={hasMetrics ? fmtUSD(metrics.total_escrowed_usd) : "$155.00"}
          sub={hasMetrics ? "Funds awaiting / processed" : "Demo benchmark"}
        />
        <StatCard
          icon={Layers}
          label="Active contracts"
          value={String(contractsRaw?.contracts?.length ?? 0).padStart(2, "0")}
          sub="Across all agents"
        />
        <StatCard
          icon={TrendingUp}
          label="Approval rate"
          value={hasMetrics ? fmtPct(metrics.success_rate) : "67%"}
          sub={hasMetrics ? "Composite score at or above 85%" : "Demo benchmark"}
          accent="text-volt-deep"
        />
        <StatCard
          icon={Clock}
          label="Avg. verification"
          value={hasMetrics ? `${(metrics.avg_arbiter_ms / 1000).toFixed(1)}s` : "4.2s"}
          sub={hasMetrics ? "Neural Arbiter scoring time" : "Illustrative demo metric"}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="card p-6 lg:col-span-3">
          <div className="mb-6 flex items-center justify-between">
            <h2 className="font-display text-base font-bold text-ink">How your escrow works</h2>
            <Chip tone="lilac">5-step flow</Chip>
          </div>
          <FlowSteps />
          <div className="mt-6 flex flex-col gap-3 rounded-2xl bg-lilac-100 p-4 sm:flex-row sm:items-center">
            <div className="flex-1">
              <p className="text-sm font-bold text-ink">Try it yourself</p>
              <p className="mt-0.5 text-xs leading-relaxed text-mute">
                Run a sample task and watch the payment decision happen.
              </p>
            </div>
            <button className="btn-plum shrink-0" onClick={() => onRunDemo("A")} disabled={running}>
              {running ? "Running…" : "Run demo"}
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="lg:col-span-2">
          <EvaluationCard evaluation={lastRun?.evaluation || null} />
        </div>
      </div>

      <div className="card">
        <div className="flex items-center justify-between px-6 py-4">
          <h2 className="font-display text-base font-bold text-ink">Recent contract activity</h2>
          <button className="btn-ghost !px-3.5 !py-2 text-xs" onClick={() => onNavigate("payments")}>
            View all <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>
        <TransactionTable
          rows={rows}
          emptyAction={
            <button className="btn-volt" onClick={() => onRunDemo("A")} disabled={running}>
              Run the demo
            </button>
          }
        />
      </div>
    </div>
  );
}
