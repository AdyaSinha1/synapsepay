import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Bot, FileSignature, Landmark, Loader2, ShieldCheck } from "lucide-react";
import EventFeed from "../components/EventFeed.jsx";
import { Chip, EmptyState, PageIntro, ScoreBar, SectionHeader, StatusChip } from "../components/ui.jsx";
import { useApp } from "../context.jsx";
import { fmtUSD, getContract, getContractEvaluations, getContractSubmissions } from "../api.js";

const STATE_STEPS = [
  { state: "FUNDED", label: "Funded", icon: Landmark },
  { state: "ACCEPTED", label: "Accepted", icon: Bot },
  { state: "SUBMITTED", label: "Submitted", icon: FileSignature },
  { state: "ARBITRATING", label: "Arbitrating", icon: ShieldCheck },
  { state: "SETTLED", label: "Settled", icon: ShieldCheck },
];

const STATE_ALIAS = { CAPTURED: "SETTLED", PARTIAL: "PARTIAL" };

function stepIndex(state) {
  const canonical = STATE_ALIAS[state] || state;
  const idx = STATE_STEPS.findIndex((s) => s.state === canonical);
  if (canonical === "REMEDIATION") return 3;
  return idx;
}

export default function ContractDetail() {
  const { id } = useParams();
  const { showError } = useApp();
  const [contract, setContract] = useState(null);
  const [evaluations, setEvaluations] = useState([]);
  const [submissions, setSubmissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [c, e, s] = await Promise.all([
        getContract(id),
        getContractEvaluations(id).catch(() => ({ evaluations: [] })),
        getContractSubmissions(id).catch(() => ({ submissions: [] })),
      ]);
      setContract(c);
      setEvaluations(e.evaluations || []);
      setSubmissions(s.submissions || []);
      setError(null);
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
    const interval = setInterval(load, 8000);
    return () => clearInterval(interval);
  }, [load]);

  const runArbiter = async () => {
    setBusy(true);
    try {
      await getContract(id);
    } finally {
      try {
        await load();
      } finally {
        setBusy(false);
      }
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-mute">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading contract…
      </div>
    );
  }

  if (error || !contract) {
    return (
      <EmptyState
        icon={ShieldCheck}
        title={error ? "Could not load contract" : "Contract not found"}
        body={error || `No contract with id ${id} exists on this server. It may belong to a different deployment, or the backend restarted with a cleared database.`}
        action={<Link className="btn-volt" to="/dashboard">Back to dashboard</Link>}
      />
    );
  }

  const c = contract.contract;
  const esc = contract.escrow;
  const receipt = esc?.receipt;
  const evaluation = evaluations[evaluations.length - 1] || null;
  const sIdx = stepIndex(c.state);
  const state = c.state || "FUNDED";

  return (
    <div className="space-y-6">
      <PageIntro
        title={c.title}
        sub={<span className="font-mono">SYN-{c.id} · hirer {c.hirer} · worker {c.worker}</span>}
        action={
          <Link to="/contracts" className="btn-ghost">
            <ArrowLeft className="h-4 w-4" /> All contracts
          </Link>
        }
      />

      <div className="card p-5">
        <div className="flex flex-wrap items-center gap-2">
          {STATE_STEPS.map((s, i) => {
            const done = i < sIdx || (i === sIdx && !["ARBITRATING"].includes(state));
            const active = i === sIdx && state !== "SETTLED";
            const doneOrCurrent = i <= sIdx;
            return (
              <div key={s.state} className="flex items-center gap-2">
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold ${
                    doneOrCurrent && state !== "DRAFT"
                      ? state === "SETTLED" && i === 4
                        ? "border-volt-deep/40 bg-volt-soft text-volt-ink"
                        : state === "PARTIAL" && i === 4
                          ? "border-sun/40 bg-sun-100 text-sun-ink"
                          : "border-lilac/40 bg-lilac-100 text-lilac-ink"
                      : "border-line bg-white text-mute/70"
                  }`}
                >
                  <s.icon className="h-3.5 w-3.5" /> {s.label}
                </span>
                {i < STATE_STEPS.length - 1 && <span className="flow-dash hidden h-0.5 w-6 sm:block" />}
              </div>
            );
          })}
          <div className="ml-auto"><StatusChip status={esc?.status || "DRAFT"} /></div>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-mute">
          {esc?.status === "AUTHORIZED" && "Funds are RESERVED on the hirer's PayPal account — not deposited. Only the arbiter's verdict can capture or release them."}
          {esc?.status === "ARBITRATING" && "The Neural Arbiter is scoring the latest submission right now."}
          {esc?.status === "REMEDIATION" && "The first submission failed near the threshold. The worker may resubmit once; no money has moved."}
          {esc?.status === "CAPTURED" && "The capture completed the charge — funds moved to the worker."}
          {esc?.status === "PARTIAL" && "A scheduled fraction was captured and the remainder released back to the hirer."}
          {esc?.status === "VOIDED" && "The hold was released — no money ever moved."}
          {esc?.status === "DRAFT" && "This contract is a draft: no PayPal reservation exists until it is funded."}
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-6 lg:col-span-2">
          <div className="card p-6">
            <SectionHeader title="Contract" sub={`Bounty ${fmtUSD(c.bounty_value)} ${c.currency} · ${c.deadline_hours || 72}h deadline`} />
            {c.description && <p className="text-xs leading-relaxed text-mute">{c.description}</p>}
            <ul className="mt-3 space-y-1.5">
              {(c.acceptance_criteria || []).map((crit) => (
                <li key={crit} className="text-xs text-mute">• {crit}</li>
              ))}
            </ul>
            <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
              <div className="rounded-lg bg-[#FCFBF7] p-2.5">
                <p className="text-mute">State</p>
                <p className="font-semibold text-ink">{state}</p>
              </div>
              <div className="rounded-lg bg-[#FCFBF7] p-2.5">
                <p className="text-mute">Mode</p>
                <p className="font-semibold text-ink">{esc?.mode === "live_sandbox" ? "Live sandbox" : "Simulated"}</p>
              </div>
            </div>
          </div>

          {receipt && (
            <div className="card p-6">
              <SectionHeader
                title="Receipt"
                sub={receipt.settlement_type === "VOID" ? "Reservation released" : "Capture completed the charge"}
                badge={<Chip tone={receipt.needs_review ? "coral" : receipt.settlement_type === "CAPTURE" ? "volt" : receipt.settlement_type === "PARTIAL_CAPTURE" ? "sun" : "coral"}>{receipt.needs_review ? "Needs review" : receipt.settlement_type}</Chip>}
              />
              <div className="space-y-1.5 text-xs">
                <div className="flex justify-between"><span className="text-mute">Amount</span><span className="font-mono text-ink">{fmtUSD(receipt.amount)}</span></div>
                {receipt.captured_amount != null && (
                  <div className="flex justify-between"><span className="text-mute">Captured</span><span className="font-mono text-ink">{fmtUSD(receipt.captured_amount)}</span></div>
                )}
                {receipt.released_amount != null && receipt.released_amount > 0 && (
                  <div className="flex justify-between"><span className="text-mute">Released</span><span className="font-mono text-ink">{fmtUSD(receipt.released_amount)}</span></div>
                )}
                <div className="flex justify-between"><span className="text-mute">Transaction</span><span className="truncate font-mono text-ink">{receipt.transaction_id}</span></div>
              </div>
              {receipt.needs_review && (
                <p className="mt-3 rounded-lg bg-coral-100 p-2.5 text-[11px] text-coral-ink">{receipt.notes}</p>
              )}
            </div>
          )}
        </div>

        <div className="space-y-6 lg:col-span-3">
          <div className="card p-6">
            <SectionHeader
              title="Submissions"
              sub={submissions.length ? `${submissions.length} submission(s) — every version is kept` : "No deliverable submitted yet."}
              action={
                esc?.status === "REMEDIATION" || ["ACCEPTED", "FUNDED"].includes(state) ? (
                  <Link to={`/contracts/${id}/workspace`} className="btn-volt !px-3.5 !py-2 text-xs">
                    Open worker workspace
                  </Link>
                ) : undefined
              }
            />
            {submissions.length > 0 && (
              <ul className="space-y-2">
                {submissions.map((s, i) => (
                  <li key={i} className="flex items-center justify-between rounded-xl border border-line bg-[#FCFBF7] px-3 py-2 text-xs">
                    <span className="text-mute">Submission #{i + 1} · {(s.submitted_at || "").slice(0, 19).replace("T", " ")}</span>
                    <span className="font-mono text-mute/70">{(s.code || "").split("\n").length} lines</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="card p-6">
            <SectionHeader title="Arbiter report" sub="Per-channel scores, rationale and decision for every round." />
            {evaluation ? (
              <div className="space-y-4">
                <div className="rounded-xl bg-lilac-100 p-4">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-lilac-ink/70">Composite</p>
                  <p className="font-display text-2xl font-extrabold text-lilac-ink">
                    {(evaluation.composite * 100).toFixed(2)}% → {evaluation.decision}
                  </p>
                </div>
                <ScoreBar label="Unit tests" value={evaluation.scores?.tests} bar="bg-volt-deep" />
                <ScoreBar label="Schema compliance" value={evaluation.scores?.schema} bar="bg-plum-700" />
                <ScoreBar label="AI review" value={evaluation.scores?.llm} bar="bg-lilac" />
                <p className="text-[11px] leading-relaxed text-mute">
                  {evaluation.llm_rationale} <span className="text-mute/60">[{evaluation.llm_provider}]</span>
                </p>
                {evaluation.remediation_plan?.length > 0 && (
                  <div className="rounded-xl border border-sun/40 bg-sun-100 p-3">
                    <p className="text-[11px] font-bold uppercase tracking-wide text-sun-ink">Remediation plan</p>
                    <ul className="mt-1 space-y-1 text-[11px] text-sun-ink/90">
                      {evaluation.remediation_plan.map((p, i) => <li key={i}>• {p}</li>)}
                    </ul>
                  </div>
                )}
                <details className="rounded-xl border border-line bg-[#FBFAF5] p-3">
                  <summary className="cursor-pointer text-[11px] font-semibold text-mute">Raw test logs</summary>
                  <div className="console mt-2 max-h-48 p-2">
                    {(evaluation.test_logs || []).map((l, i) => (
                      <p key={i} className={l.startsWith("[PASS]") ? "text-volt-ink" : l.startsWith("[FAIL]") ? "text-coral" : "text-mute"}>{l}</p>
                    ))}
                  </div>
                </details>
              </div>
            ) : (
              <p className="text-xs text-mute">No arbitration yet — submit a deliverable, then run the arbiter.</p>
            )}
          </div>

          <div className="card p-6">
            <SectionHeader title="Audit trail" sub="Append-only record of every arbitration round." badge={<Chip tone="slate">{evaluations.length} rounds</Chip>} />
            {evaluations.length === 0 ? (
              <p className="text-xs text-mute">Nothing recorded yet.</p>
            ) : (
              <ul className="space-y-2">
                {evaluations.map((ev, i) => (
                  <li key={i} className="flex items-center justify-between gap-2 rounded-xl border border-line bg-[#FCFBF7] px-3 py-2">
                    <span className="text-xs font-semibold text-ink">Round {i + 1} · S = {Number(ev.composite).toFixed(4)}</span>
                    <Chip tone={ev.decision === "CAPTURE" ? "volt" : ev.decision === "PARTIAL" ? "sun" : "coral"}>{ev.decision}</Chip>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="card p-6">
            <SectionHeader title="Live event feed" sub="Contract events stream here in real time." />
            <EventFeed events={[]} height="h-40" placeholder="Cycle events for this contract appear here during arbitration." />
          </div>
        </div>
      </div>
    </div>
  );
}
