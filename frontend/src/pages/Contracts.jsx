import { useState } from "react";
import { Check, Loader2, Play, Sparkles } from "lucide-react";
import { Chip, PageIntro, SectionHeader, StatusChip } from "../components/ui.jsx";
import { fmtUSD } from "../api.js";

const inputCls = "input";

export default function Contracts({ scenarios, contracts, running, onCreateAndRun, onRunCycle, lastEscrow }) {
  const [form, setForm] = useState({
    title: "Refactor billing microservice",
    bounty: 25,
    criteria: "Expose charge(notional, tier)\nHandle zero and negative inputs",
    workerCode: "def charge(notional, tier):\n    \"\"\"Charge 1% of notional.\"\"\"\n    return round(notional * 0.01, 2)\n",
    testCode: "def test_basic():\n    assert charge(100, 'std') == 1.0\n\ndef test_rounding():\n    assert charge(33.333, 'std') == 0.33\n",
    runNow: true,
  });
  const [busy, setBusy] = useState(false);

  const update = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const busyOrRunning = busy || running;

  const submit = async () => {
    setBusy(true);
    try {
      await onCreateAndRun({
        title: form.title,
        description: "Custom task created from the Contracts page",
        bounty_value: Number(form.bounty),
        currency: "USD",
        acceptance_criteria: form.criteria.split("\n").map((s) => s.trim()).filter(Boolean),
        deliverable_schema: { type: "code", required_functions: [] },
        test_code: form.testCode,
        worker_code: form.workerCode,
        run_now: form.runNow,
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageIntro
        title="Contracts"
        sub="Write the rules, set the bounty, and lock escrow. The Neural Arbiter enforces every contract automatically."
      />

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="card p-6 lg:col-span-3">
          <SectionHeader
            title="New contract"
            sub="The hirer agent defines the task. Funds lock the moment you create it."
            badge={<Chip tone="lilac">Step 1 of 5</Chip>}
          />
          <div className="space-y-4">
            <div className="grid grid-cols-4 gap-3">
              <label className="col-span-3 block">
                <span className="mb-1.5 block text-xs font-medium text-mute">Task title</span>
                <input className={inputCls} value={form.title} onChange={update("title")} />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-mute">Bounty (USD)</span>
                <input type="number" min="1" className={inputCls} value={form.bounty} onChange={update("bounty")} />
              </label>
            </div>
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-mute">Acceptance criteria — one per line</span>
              <textarea rows={2} className={`${inputCls} font-mono text-xs`} value={form.criteria} onChange={update("criteria")} />
            </label>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-mute">Worker code (Python)</span>
                <textarea rows={6} className={`${inputCls} font-mono text-xs`} value={form.workerCode} onChange={update("workerCode")} />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-mute">Contract unit tests</span>
                <textarea rows={6} className={`${inputCls} font-mono text-xs`} value={form.testCode} onChange={update("testCode")} />
              </label>
            </div>
            <label className="flex items-center gap-2 text-xs text-mute">
              <input
                type="checkbox"
                checked={form.runNow}
                onChange={(e) => setForm((f) => ({ ...f, runNow: e.target.checked }))}
                className="h-4 w-4 rounded border-line accent-[#8B7BE8]"
              />
              Run the full escrow cycle right after authorizing
            </label>
            <button className="btn-volt w-full" onClick={submit} disabled={busyOrRunning}>
              {busyOrRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {form.runNow ? "Authorize escrow & run cycle" : "Authorize escrow"}
            </button>
            <p className="text-[11px] leading-relaxed text-mute/80">
              No tests means an automatic void verdict — the arbiter always pays with evidence.
            </p>

            {lastEscrow && (
              <div className="fade-up rounded-xl border border-volt-deep/40 bg-volt-soft p-4">
                <p className="text-xs font-bold uppercase tracking-wide text-volt-ink">Escrow authorized</p>
                <p className="mt-1.5 font-mono text-[11px] text-mute">Order {lastEscrow.order_id}</p>
                <p className="font-mono text-[11px] text-mute">Authorization {lastEscrow.authorization_id}</p>
                <p className="mt-1 text-[11px] text-mute">
                  {fmtUSD(lastEscrow.amount)} locked · status {lastEscrow.status}
                </p>
              </div>
            )}
          </div>
        </div>

        <div className="space-y-6 lg:col-span-2">
          <div className="card p-6">
            <SectionHeader title="Quick start" sub="One click runs the full cycle." />
            <div className="space-y-2.5">
              {scenarios.map((s) => (
                <button
                  key={s.id}
                  onClick={() => onCreateAndRun({ scenario_id: s.id, run_now: true })}
                  disabled={busyOrRunning}
                  className="flex w-full items-center justify-between gap-3 rounded-xl border border-line bg-[#FCFBF7] px-4 py-3 text-left transition hover:border-lilac/50 hover:bg-lilac-100/40 disabled:opacity-50"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-semibold text-ink">{s.subtitle}</span>
                    <span className="block text-[11px] text-mute">{fmtUSD(s.amount)} · {s.name.split("—")[0].trim()}</span>
                  </span>
                  <Play className="h-4 w-4 shrink-0 text-lilac" />
                </button>
              ))}
            </div>
          </div>

          <div className="card p-6">
            <SectionHeader title="Your contracts" sub="Newest first." />
            {contracts.length === 0 ? (
              <p className="text-xs leading-relaxed text-mute">
                Nothing here yet — create a contract or run a quick-start scenario above.
              </p>
            ) : (
              <ul className="space-y-2.5">
                {contracts.slice(0, 6).map((c) => (
                  <li key={c.id} className="rounded-xl border border-line px-4 py-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-sm font-medium text-ink">{c.title}</p>
                      <StatusChip status={c.escrow?.status || "PENDING"} />
                    </div>
                    <div className="mt-1 flex items-center justify-between">
                      <p className="font-mono text-[11px] text-mute">SYN-{c.id} · {fmtUSD(c.bounty_value)}</p>
                      {c.escrow?.status === "AUTHORIZED" && (
                        <button
                          className="inline-flex items-center gap-1 text-[11px] font-semibold text-lilac-ink hover:text-lilac"
                          onClick={() => onRunCycle(c.id)}
                          disabled={busyOrRunning}
                        >
                          <Play className="h-3 w-3" /> Run cycle
                        </button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
