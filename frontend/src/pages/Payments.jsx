import { CircleDollarSign, Clock, Coins, TrendingDown, Wallet } from "lucide-react";
import TransactionTable from "../components/TransactionTable.jsx";
import { PageIntro, StatCard } from "../components/ui.jsx";
import { fmtUSD, zipContracts } from "../api.js";

export default function Payments({ metrics, contractsRaw, running, onRunDemo, onNavigate }) {
  const m = metrics;
  const hasData = Boolean(m && m.cycles > 0);
  const rows = zipContracts(contractsRaw);

  return (
    <div className="space-y-6">
      <PageIntro
        title="Payments"
        sub="Every authorization, capture, and void — with the exact PayPal transaction IDs behind it."
      />

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard
          icon={Wallet}
          label="Total authorized"
          value={hasData ? fmtUSD(m.total_escrowed_usd) : "$0.00"}
          sub="Locked across all contracts"
        />
        <StatCard
          icon={CircleDollarSign}
          label="Captured"
          value={hasData ? fmtUSD(m.captured_usd) : "$0.00"}
          sub={hasData ? `${m.captures} full + ${m.partials} partial payouts${m.needs_review ? ` · ${m.needs_review} flagged for review` : ""}` : "No payouts yet"}
          accent="text-volt-deep"
        />
        <StatCard
          icon={TrendingDown}
          label="Refunded / released"
          value={hasData ? fmtUSD(m.refunded_usd + m.released_usd) : "$0.00"}
          sub={hasData ? `${m.voids} voids · ${fmtUSD(m.released_usd)} from partials` : "No voids yet"}
          accent="text-coral"
        />
        <StatCard
          icon={Clock}
          label="Avg. settlement"
          value={hasData ? `${m.avg_settlement_ms} ms` : "—"}
          sub="PayPal API round-trip"
        />
      </div>

      <div className="card">
        <div className="flex items-center justify-between px-6 py-4">
          <h2 className="font-display text-base font-bold text-ink">Transaction ledger</h2>
          <span className="font-mono text-[10px] uppercase tracking-wider text-mute/60">
            {rows.length} contract{rows.length === 1 ? "" : "s"}
          </span>
        </div>
        <TransactionTable
          rows={rows}
          emptyAction={
            <div className="flex justify-center gap-2">
              <button className="btn-volt" onClick={() => onRunDemo("A")} disabled={running}>
                Run demo scenario
              </button>
              <button className="btn-ghost" onClick={() => onNavigate("studio")}>
                Open Demo Studio
              </button>
            </div>
          }
        />
      </div>

      <div className="card p-5">
        <h2 className="mb-2 font-display text-sm font-bold text-ink">How the escrow actually works</h2>
        <div className="grid gap-3 text-[11px] leading-relaxed text-mute sm:grid-cols-3">
          <div className="rounded-xl border border-lilac/30 bg-lilac-100/50 p-3">
            <p className="text-xs font-bold text-lilac-ink">1 · AUTHORIZED = reserved</p>
            <p className="mt-1">
              The Orders API <span className="font-mono">AUTHORIZE</span> places a hold on the hirer's PayPal account.
              Funds are <span className="font-semibold text-ink">reserved, not deposited</span> — no money has moved yet.
            </p>
          </div>
          <div className="rounded-xl border border-volt-deep/30 bg-volt-soft p-3">
            <p className="text-xs font-bold text-volt-ink">2 · CAPTURE = charge</p>
            <p className="mt-1">
              Only a passing (or partial) verdict calls <span className="font-mono">capture</span>, completing the
              charge for that amount. Partial captures release the remainder automatically.
            </p>
          </div>
          <div className="rounded-xl border border-coral/30 bg-coral-100 p-3">
            <p className="text-xs font-bold text-coral-ink">3 · VOID = release</p>
            <p className="mt-1">
              A failed verdict calls <span className="font-mono">void</span>, releasing the hold with nothing charged.
              Expired or duplicate requests are handled idempotently.
            </p>
          </div>
        </div>
      </div>

      <div className="card p-5">
        <p className="text-[11px] leading-relaxed text-mute">
          <Coins className="mr-1 inline h-3.5 w-3.5 text-volt-deep" />
          All money in this demo moves on PayPal's sandbox rails (or a labelled simulator when sandbox keys are not
          configured) — no real funds change hands. Every row above shows its mode. Scores are AI arbitration evidence,
          not probabilities.
        </p>
      </div>
    </div>
  );
}
