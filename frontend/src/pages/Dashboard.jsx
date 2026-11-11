import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Asterisk, Clock, Eye, Layers, TrendingUp, Wallet } from "lucide-react";
import EvaluationCard from "../components/EvaluationCard.jsx";
import TransactionTable from "../components/TransactionTable.jsx";
import { Chip, PageIntro, StatCard } from "../components/ui.jsx";
import { useApp } from "../context.jsx";
import { fmtPct, fmtUSD } from "../api.js";

export default function Dashboard() {
  const { user, metrics, contracts, lastRun, running, runScenario, contractsRaw, showError } = useApp();
  const navigate = useNavigate();
  const role = user?.role || "hirer";
  const hasMetrics = Boolean(metrics && metrics.cycles > 0);
  const isWorker = role === "worker";

  const myJobs = isWorker ? contracts.filter((c) => c.worker === user.username) : [];
  const myEarnings = isWorker
    ? myJobs.reduce((sum, c) => sum + (c.escrow?.receipt?.captured_amount || 0), 0)
    : 0;

  const counts = contracts.reduce((acc, c) => {
    const key = c.escrow?.status || "DRAFT";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <PageIntro
        title={
          <span className="flex items-center gap-2">
            {isWorker ? "Your workbench" : "Good to see you."} <Asterisk className="h-6 w-6 text-lilac" />
          </span>
        }
        sub={
          isWorker
            ? "Jobs you have accepted and what they paid out. Claim new work from the Open Board."
            : "Here's what's happening across your agent economy."
        }
        action={
          !isWorker ? (
            <Link className="btn-volt" to="/contracts/new">
              + New contract
            </Link>
          ) : (
            <Link className="btn-volt" to="/board">
              Browse open board
            </Link>
          )
        }
      />

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        {isWorker ? (
          <>
            <StatCard icon={Layers} label="Accepted jobs" value={String(myJobs.length).padStart(2, "0")} sub="Contracts assigned to you" />
            <StatCard icon={Wallet} label="Earnings" value={fmtUSD(myEarnings)} sub="Captured payouts on your jobs" accent="text-volt-deep" />
            <StatCard icon={Eye} label="Open on board" value={String(contracts.filter((c) => c.escrow?.status === "AUTHORIZED" && c.state === "FUNDED").length)} sub="Funded, unclaimed contracts" />
            <StatCard icon={Clock} label="Avg. verification" value={hasMetrics ? `${(metrics.avg_arbiter_ms / 1000).toFixed(1)}s` : "—"} sub="Neural Arbiter scoring time" />
          </>
        ) : (
          <>
            <StatCard icon={Eye} label="Total authorized" value={hasMetrics ? fmtUSD(metrics.total_escrowed_usd) : "$155.00"} sub={hasMetrics ? "Funds awaiting / processed" : "Demo benchmark"} />
            <StatCard icon={Layers} label="Active contracts" value={String(contracts.length).padStart(2, "0")} sub="Across all agents" />
            <StatCard icon={TrendingUp} label="Approval rate" value={hasMetrics ? fmtPct(metrics.success_rate) : "67%"} sub={hasMetrics ? "Composite score at or above 85%" : "Demo benchmark"} accent="text-volt-deep" />
            <StatCard icon={Clock} label="Avg. verification" value={hasMetrics ? `${(metrics.avg_arbiter_ms / 1000).toFixed(1)}s` : "4.2s"} sub={hasMetrics ? "Neural Arbiter scoring time" : "Illustrative demo metric"} />
          </>
        )}
      </div>

      <div className="card p-5">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">Contracts by status</h2>
        <div className="flex flex-wrap gap-2">
          {Object.entries(counts).length === 0 && <p className="text-xs text-mute">No contracts yet.</p>}
          {Object.entries(counts).map(([status, n]) => (
            <Chip key={status} tone={status === "CAPTURED" ? "volt" : status === "VOIDED" ? "coral" : status === "PARTIAL" ? "sun" : "lilac"} dot>
              {status} × {n}
            </Chip>
          ))}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className={`card p-6 ${isWorker ? "lg:col-span-5" : "lg:col-span-3"}`}>
          <div className="mb-6 flex items-center justify-between">
            <h2 className="font-display text-base font-bold text-ink">How your escrow works</h2>
            <Chip tone="lilac">5-step flow</Chip>
          </div>
          <div className="text-sm text-mute">
            Hire → fund → deliver → arbitrate → settle. The PayPal hold reserves funds; only the
            arbiter's verdict moves money, and the LLM can never decide alone.
          </div>
          {!isWorker && (
            <div className="mt-6 flex flex-col gap-3 rounded-2xl bg-lilac-100 p-4 sm:flex-row sm:items-center">
              <div className="flex-1">
                <p className="text-sm font-bold text-ink">Try it yourself</p>
                <p className="mt-0.5 text-xs leading-relaxed text-mute">
                  Run a sample task and watch the payment decision happen.
                </p>
              </div>
              <button className="btn-plum shrink-0" onClick={() => runScenario("A").catch(showError)} disabled={running}>
                {running ? "Running…" : "Run demo"} <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          )}
        </div>

        {!isWorker && (
          <div className="lg:col-span-2">
            <EvaluationCard evaluation={lastRun?.evaluation || null} />
          </div>
        )}
      </div>

      <div className="card">
        <div className="flex items-center justify-between px-6 py-4">
          <h2 className="font-display text-base font-bold text-ink">
            {isWorker ? "Your contracts" : "Recent contract activity"}
          </h2>
          <button className="btn-ghost !px-3.5 !py-2 text-xs" onClick={() => navigate(isWorker ? "/board" : "/payments")}>
            View all <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>
        <TransactionTable
          rows={isWorker ? myJobs : contracts.slice(0, 4)}
          emptyAction={
            <button className="btn-volt" onClick={() => runScenario("A").catch(showError)} disabled={running}>
              Run the demo
            </button>
          }
        />
      </div>
    </div>
  );
}
